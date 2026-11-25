from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app import games
from app.models import Candidate, GameEntry, Job, Link, PublishedGame, Word

from .test_studio import API, add_category, add_words, ok, studio  # noqa: F401


@pytest.fixture
def filled(studio):  # noqa: F811
    for i in range(8):
        category = add_category(studio, f"c{i}", is_topical=i % 2 == 0, difficulty=i % 4)
        add_words(studio, category, *[f"w{i}-{j}" for j in range(6)], f"w{(i + 1) % 8}-0")
    return studio


def generate(client, count=5):
    job = ok(client.post(f"{API}/jobs", json={"count": count}))
    return ok(client.get(f"{API}/jobs/{job['id']}"))


def candidates(client):
    return ok(client.get(f"{API}/candidates"))["items"]


def test_generates_and_saves_candidates(filled):
    job = generate(filled)
    assert job["status"] == "done", job
    assert job["result"]["created"] == 5 and job["result"]["problem"] is None
    saved = candidates(filled)
    assert len(saved) == 5
    assert all(len(games.word_ids(c["game"])) == 16 for c in saved)

    generate(filled)
    sets = [games.word_ids(c["game"]) for c in candidates(filled)]
    assert len(sets) == len(set(sets)) == 10


def test_empty_graph_explains_itself(studio):  # noqa: F811
    job = generate(studio)
    assert job["status"] == "done"
    assert "There are 0" in job["result"]["problem"]


def test_candidates_survive_edits(filled):
    generate(filled, 1)
    before = candidates(filled)
    for group in before[0]["game"]["groups"]:
        ok(filled.delete(f"{API}/categories/{group['category_id']}"))
    assert candidates(filled) == before


def test_deleted_items_are_not_used(filled):
    page = ok(filled.get(f"{API}/categories"))["items"]
    gone = page[0]["id"]
    ok(filled.delete(f"{API}/categories/{gone}"))
    generate(filled, 10)
    used = {g["category_id"] for c in candidates(filled) for g in c["game"]["groups"]}
    assert used and gone not in used


def test_published_meanings_are_not_reused(filled, music_db):
    links = music_db.scalars(
        select(Link).join(Word, Word.id == Link.word_id).where(Word.text.like("w%-3"))
    ).all()
    game = PublishedGame(snapshot={}, serve_date=datetime.now(UTC).date())
    music_db.add(game)
    music_db.flush()
    for x in links:
        music_db.add(
            GameEntry(game_id=game.id, link_id=x.id, word_id=x.word_id, category_id=x.category_id)
        )
    music_db.commit()
    generate(filled, 10)
    used = {
        w["link_id"] for c in candidates(filled) for g in c["game"]["groups"] for w in g["words"]
    }
    assert used and not used & {x.id for x in links}


def test_next_free_date(filled, music_db):
    today = datetime.now(UTC).date()
    for days in (0, 1, 2, 4):
        music_db.add(PublishedGame(snapshot={}, serve_date=today + timedelta(days=days)))
    music_db.flush()
    assert games.next_free_date(music_db, today) == today + timedelta(days=3)


def test_one_job_at_a_time_and_stuck_jobs_expire(filled, music_db):
    music_db.add(Job(kind="generate", params={"count": 1}, status="running"))
    music_db.commit()
    stuck = music_db.scalar(select(Job.id))
    assert filled.post(f"{API}/jobs", json={}).status_code == 409

    music_db.execute(update(Job).values(created_at=datetime.now(UTC) - timedelta(hours=1)))
    music_db.commit()
    assert ok(filled.get(f"{API}/jobs/{stuck}"))["status"] == "failed"
    assert generate(filled)["status"] == "done"
    assert ok(filled.get(f"{API}/jobs/{stuck}"))["error"] == "The job was interrupted."


def test_failure_is_reported(filled, music_db, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(games, "generate", broken)
    job = generate(filled)
    assert (job["status"], job["error"]) == ("failed", "Something went wrong.")
    assert music_db.scalar(select(Candidate.id)) is None


@pytest.mark.parametrize("count", [0, 21, "x"])
def test_bad_count(studio, count):  # noqa: F811
    assert studio.post(f"{API}/jobs", json={"count": count}).status_code == 422


def test_suggestions(studio):  # noqa: F811
    add_words(studio, add_category(studio, "nearly"), "a", "b", "c")
    add_words(studio, add_category(studio, "alone"), "d", "e", "f", "g")
    found = ok(studio.get(f"{API}/suggestions"))
    assert [c["name"] for c in found["almost_usable"]] == ["nearly"]
    assert [c["name"] for c in found["isolated"]] == ["alone"]

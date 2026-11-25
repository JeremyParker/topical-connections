import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app import cli
from app.config import Settings, load_topics
from app.models import Category, GameEntry, Link, PublishedGame, User, Word

from .test_auth import EMAIL, request_code, sign_in, verify


def test_slug_selects_topic(music, biology):
    assert music.get("/topic").json()["name"] == "music game"
    assert biology.get("/topic").json()["name"] == "biology game"


@pytest.mark.parametrize("path", ["topic", "auth/me", "studio/words"])
@pytest.mark.parametrize("slug", ["chess", "MUSIC", "music%2F", "%2e%2e"])
def test_unknown_topic(app, slug, path):
    client = TestClient(app, base_url="https://api.test")
    assert client.get(f"/api/{slug}/{path}").status_code == 404


def test_there_is_no_default_topic(app):
    client = TestClient(app, base_url="https://api.test")
    for path in ("topic", "auth/me", "studio/words"):
        assert client.get(f"/api/{path}").status_code == 404
    assert client.get("/healthz").status_code == 200


def test_host_header_is_irrelevant(music):
    for host in ("biology.test", "anything.example"):
        assert music.get("/topic", headers={"Host": host}).json()["name"] == "music game"


def test_accounts_are_separate(music, biology, mailer, biology_db):
    sign_in(music, mailer)
    assert biology_db.scalar(select(func.count()).select_from(User)) == 0
    token = music.cookies["__Host-session-music"]
    for name in ("__Host-session-music", "__Host-session-biology"):
        biology.cookies.set(name, token)
        assert biology.get("/auth/me").status_code == 401


def test_signed_in_to_two_topics_on_one_host(music, biology, mailer):
    biology.cookies = music.cookies  # as in one browser
    sign_in(music, mailer, "m@example.com")
    biology.cookies = music.cookies
    sign_in(biology, mailer, "b@example.com")
    both = {**music.cookies, **biology.cookies}
    music.cookies = biology.cookies = both
    assert music.get("/auth/me").json()["email"] == "m@example.com"
    assert biology.get("/auth/me").json()["email"] == "b@example.com"
    response = music.post("/auth/logout")
    assert "__Host-session-music=" in response.headers["set-cookie"]
    assert "biology" not in response.headers["set-cookie"]
    music.cookies = both
    assert music.get("/auth/me").status_code == 401
    assert biology.get("/auth/me").status_code == 200


def test_code_does_not_work_on_another_topic(music, biology, mailer):
    challenge = request_code(music)
    assert verify(biology, challenge, mailer.sent[-1][2]).status_code == 400


def test_rate_limits_are_separate(music, biology, mailer):
    for _ in range(5):
        request_code(music)
    request_code(biology)


def test_other_topics_origin_is_rejected(music):
    ok = music.get("/topic", headers={"Origin": "https://music.test"})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "https://music.test"
    for origin in ("https://biology.test", "https://evil.test", "null"):
        response = music.post("/auth/code", json={"email": EMAIL}, headers={"Origin": origin})
        assert response.status_code == 403


def test_one_topic_can_be_deployed_alone(settings):
    alone = settings.model_copy(update={"enabled_topics": "music"})
    assert [t.slug for t in load_topics(alone)] == ["music"]
    with pytest.raises(ValueError, match="unknown topics"):
        load_topics(settings.model_copy(update={"enabled_topics": "chess"}))


@pytest.mark.parametrize("slug", ["Music", "a/b", "a b", "a;b", ""])
def test_invalid_slugs_are_rejected(settings, tmp_path, slug):
    path = tmp_path / "topics.toml"
    path.write_text(f'["{slug}"]\nname = "x"\n')
    with pytest.raises(ValueError, match="Invalid topic slugs"):
        load_topics(settings.model_copy(update={"topics_file": path}))


def test_production_refuses_to_log_codes():
    with pytest.raises(ValidationError, match="console"):
        Settings(environment="production", secret_key="x" * 32, email_backend="console")


def test_migrations_match_models(settings):
    for topic in load_topics(settings):
        command.check(cli.alembic_config(topic.database_url))


def test_set_role_invites_and_updates(settings, app, music_db):
    topic = next(t for t in load_topics(settings) if t.slug == "music")
    cli.set_role(topic, "New@Example.com", "contributor")
    cli.set_role(topic, "new@example.com", "admin")
    user = music_db.scalars(select(User)).one()
    assert (user.email, user.role) == ("new@example.com", "admin")


def add_graph(db):
    bass = Word(text="Bass")
    instruments = Category(name="instruments", difficulty=0, is_topical=True)
    fish = Category(name="fish", difficulty=1, is_topical=False)
    db.add_all([bass, instruments, fish])
    db.flush()
    link = Link(word_id=bass.id, category_id=instruments.id)
    db.add(link)
    db.flush()
    return bass, instruments, fish, link


def test_words_unique_ignoring_case_until_deleted(music_db):
    bass, *_ = add_graph(music_db)
    bass.deleted_at = func.now()
    music_db.flush()
    music_db.add(Word(text="BASS"))
    music_db.flush()
    music_db.add(Word(text="bass"))
    with pytest.raises(IntegrityError):
        music_db.flush()


def test_game_entry_ids_must_agree(music_db):
    bass, instruments, fish, link = add_graph(music_db)
    game = PublishedGame(snapshot={})
    music_db.add(game)
    music_db.flush()
    ids = {"game_id": game.id, "word_id": bass.id, "link_id": link.id}
    with pytest.raises(IntegrityError):
        with music_db.begin_nested():
            music_db.add(GameEntry(**ids, category_id=fish.id))
            music_db.flush()
    music_db.add(GameEntry(**ids, category_id=instruments.id))
    music_db.flush()

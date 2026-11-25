from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, update

from app.models import Contribution, Link, User, Word

from .test_auth import sign_in

API = "/studio"


def sign_in_as(client, mailer, db, role):
    sign_in(client, mailer)
    db.execute(update(User).values(role=role))
    db.commit()


@pytest.fixture
def studio(music, mailer, music_db):
    sign_in_as(music, mailer, music_db, "contributor")
    return music


def ok(response):
    assert response.is_success, response.text
    return response.json() if response.content else None


def add_category(client, name="instruments", is_topical=True, difficulty=0, **extra):
    body = {"name": name, "is_topical": is_topical, "difficulty": difficulty, **extra}
    return ok(client.post(f"{API}/categories", json=body))["id"]


def add_words(client, category_id, *texts):
    return ok(client.post(f"{API}/categories/{category_id}/words", json={"texts": texts}))


def words_in(client, category_id):
    return ok(client.get(f"{API}/categories/{category_id}"))["words"]


def word_id(client, text):
    items = ok(client.get(f"{API}/words", params={"search": text}))["items"]
    return items[0]["id"]


ROUTES = [
    ("GET", "/summary"),
    ("GET", "/words"),
    ("POST", "/words"),
    ("GET", "/words/1"),
    ("PATCH", "/words/1"),
    ("DELETE", "/words/1"),
    ("GET", "/categories"),
    ("POST", "/categories"),
    ("GET", "/categories/1"),
    ("PATCH", "/categories/1"),
    ("DELETE", "/categories/1"),
    ("POST", "/categories/1/words"),
    ("POST", "/links"),
    ("PATCH", "/links/1"),
    ("DELETE", "/links/1"),
    ("POST", "/jobs"),
    ("GET", "/jobs/1"),
    ("GET", "/candidates"),
    ("GET", "/suggestions"),
]


def test_access_checks_cover_every_route(app):
    prefix = "/api/{topic_slug}/studio"
    paths = app.openapi()["paths"]
    found = {
        (method.upper(), path.removeprefix(prefix))
        for path, methods in paths.items()
        if path.startswith(prefix)
        for method in methods
    }
    assert len(found) == len(ROUTES)


@pytest.mark.parametrize("method,path", ROUTES)
def test_players_have_no_access(music, mailer, method, path):
    assert music.request(method, API + path, json={}).status_code == 401
    sign_in(music, mailer)
    assert music.request(method, API + path, json={}).status_code == 403


def test_empty_database(studio):
    assert set(ok(studio.get(f"{API}/summary")).values()) == {0}
    assert ok(studio.get(f"{API}/words")) == {"total": 0, "items": []}
    assert ok(studio.get(f"{API}/categories")) == {"total": 0, "items": []}


def test_bulk_add_reports_what_happened(studio):
    instruments, fish = add_category(studio), add_category(studio, "fish", False)
    assert add_words(studio, instruments, "Bass", " French   horn ", "", "bass", "x" * 51) == {
        "created": ["Bass", "French horn"],
        "linked": [],
        "already_there": [],
        "invalid": ["x" * 51],
    }
    assert add_words(studio, fish, "BASS", "Sole")["linked"] == ["Bass"]
    assert add_words(studio, fish, "bass")["already_there"] == ["Bass"]


def test_words_keep_capitals_and_can_be_short(studio):
    category = add_category(studio)
    add_words(studio, category, "DJ", "C", "Björk", "Björk")
    assert [w["text"] for w in words_in(studio, category)] == ["Björk", "C", "DJ"]


def test_topical_is_derived_from_categories(studio):
    instruments, fish = add_category(studio), add_category(studio, "fish", False)
    add_words(studio, instruments, "Bass")
    add_words(studio, fish, "Bass", "Sole")
    words = {w["text"]: w for w in ok(studio.get(f"{API}/words"))["items"]}
    assert words["Bass"]["is_topical"] and not words["Sole"]["is_topical"]
    ok(studio.patch(f"{API}/categories/{instruments}", json={"is_topical": False}))
    assert not ok(studio.get(f"{API}/words/{words['Bass']['id']}"))["is_topical"]


def test_lists_that_show_what_needs_work(studio):
    instruments, fish = add_category(studio), add_category(studio, "fish", False)
    add_words(studio, instruments, "Bass", "Drum", "Viola", "Horn")
    add_words(studio, fish, "Bass")
    needs = ok(studio.get(f"{API}/categories", params={"only": "needs_words"}))
    assert [c["name"] for c in needs["items"]] == ["fish"]
    one = ok(studio.get(f"{API}/words", params={"only": "one_meaning"}))
    assert {w["text"] for w in one["items"]} == {"Drum", "Viola", "Horn"}
    assert ok(studio.get(f"{API}/summary")) == {
        "words": 4,
        "categories": 2,
        "links": 5,
        "usable_categories": 1,
        "categories_needing_words": 1,
        "words_with_one_meaning": 3,
    }
    assert {w["text"]: w["meanings"] for w in words_in(studio, instruments)}["Bass"] == 2


def test_search_ranks_and_escapes(studio):
    category = add_category(studio)
    add_words(studio, category, "Snare drum", "Drummer", "drum", "100%")

    def search(text):
        items = ok(studio.get(f"{API}/words", params={"search": text}))["items"]
        return [w["text"] for w in items]

    assert search("DRUM") == ["drum", "Drummer", "Snare drum"]
    assert search("%") == ["100%"]
    assert search("_") == []


def test_paging(studio):
    category = add_category(studio)
    add_words(studio, category, *[f"w{i}" for i in range(60)])
    first = ok(studio.get(f"{API}/words"))
    second = ok(studio.get(f"{API}/words", params={"offset": 50}))
    assert first["total"] == 60
    assert len({w["id"] for w in first["items"] + second["items"]}) == 60


def test_duplicates_are_refused(studio):
    add_category(studio)
    body = {"name": " Instruments ", "is_topical": True, "difficulty": 0}
    assert studio.post(f"{API}/categories", json=body).status_code == 409
    drum = ok(studio.post(f"{API}/words", json={"text": "Drum"}))["id"]
    assert studio.post(f"{API}/words", json={"text": "drum"}).status_code == 409
    ok(studio.post(f"{API}/words", json={"text": "Horn"}))
    assert studio.patch(f"{API}/words/{drum}", json={"text": "HORN"}).status_code == 409
    ok(studio.patch(f"{API}/words/{drum}", json={"text": "DRUM"}))  # its own name is fine


def test_links(studio):
    category = add_category(studio)
    drum = ok(studio.post(f"{API}/words", json={"text": "Drum"}))["id"]
    body = {"word_id": drum, "category_id": category}
    link = ok(studio.post(f"{API}/links", json=body))["id"]
    assert studio.post(f"{API}/links", json=body).status_code == 409
    ok(studio.patch(f"{API}/links/{link}", json={"difficulty_override": 3}))
    ok(studio.patch(f"{API}/links/{link}", json={"example_sentence": "Hit it."}))
    row = ok(studio.get(f"{API}/words/{drum}"))["categories"][0]
    assert (row["difficulty_override"], row["example_sentence"]) == (3, "Hit it.")
    ok(studio.patch(f"{API}/links/{link}", json={"difficulty_override": None}))
    assert words_in(studio, category)[0]["difficulty_override"] is None
    ok(studio.delete(f"{API}/links/{link}"))
    assert words_in(studio, category) == []
    ok(studio.get(f"{API}/words/{drum}"))  # the word itself stays


def test_deleting_hides_links_and_adding_back_keeps_ids(studio):
    category = add_category(studio)
    add_words(studio, category, "Drum", "Horn")
    before = {w["text"]: (w["word_id"], w["link_id"]) for w in words_in(studio, category)}
    ok(studio.delete(f"{API}/words/{before['Drum'][0]}"))
    assert [w["text"] for w in words_in(studio, category)] == ["Horn"]
    assert studio.get(f"{API}/words/{before['Drum'][0]}").status_code == 404

    assert add_words(studio, category, "drum")["created"] == ["drum"]
    after = {w["text"]: (w["word_id"], w["link_id"]) for w in words_in(studio, category)}
    assert after["drum"] == before["Drum"]

    ok(studio.delete(f"{API}/categories/{category}"))
    assert ok(studio.get(f"{API}/summary"))["links"] == 0
    assert add_category(studio, "Instruments", difficulty=2) == category
    detail = ok(studio.get(f"{API}/categories/{category}"))
    assert (detail["name"], detail["difficulty"], detail["words"]) == ("Instruments", 2, [])


def test_contributions_are_recorded(studio, music_db):
    category = add_category(studio)
    add_words(studio, category, "Drum")
    ok(studio.patch(f"{API}/categories/{category}", json={"difficulty": 1}))
    ok(studio.patch(f"{API}/categories/{category}", json={"difficulty": 1}))  # no change
    ok(studio.delete(f"{API}/words/{word_id(studio, 'Drum')}"))
    rows = music_db.scalars(select(Contribution).order_by(Contribution.id)).all()
    assert [(r.action, r.entity_type) for r in rows] == [
        ("create", "category"),
        ("create", "word"),
        ("create", "link"),
        ("update", "category"),
        ("delete", "link"),
        ("delete", "word"),
    ]
    assert rows[3].details == {"difficulty": {"from": 0, "to": 1}}
    assert len({r.user_id for r in rows}) == 1


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/words", {"text": "   "}),
        ("POST", "/words", {"text": "x" * 51}),
        ("POST", "/words", {"text": "a\u0000b"}),
        ("POST", "/categories", {"name": "x", "is_topical": True, "difficulty": 4}),
        ("POST", "/categories", {"name": "x", "difficulty": 1}),
        ("PATCH", "/categories/1", {"name": None}),
        ("PATCH", "/categories/1", {"is_topical": None}),
        ("PATCH", "/links/1", {"difficulty_override": -1}),
        ("POST", "/categories/1/words", {"texts": []}),
        ("POST", "/categories/1/words", {"texts": ["x"] * 201}),
        ("GET", "/words/99999999999", None),
    ],
)
def test_bad_input_is_refused(studio, method, path, body):
    category = add_category(studio)
    add_words(studio, category, "Drum")
    assert studio.request(method, API + path, json=body).status_code == 422


def test_odd_characters_dont_crash(studio):
    category = add_category(studio, notes="a\u0000b")
    assert add_words(studio, category, "a\u0000b", "ok")["invalid"] == ["a\u0000b"]
    ok(studio.get(f"{API}/words", params={"search": "\u0000"}))
    ok(studio.get(f"{API}/categories", params={"search": "\u0000"}))


def test_parallel_edits_dont_conflict(studio, music_db):
    categories = [add_category(studio, f"c{i}") for i in range(4)]
    texts = [f"w{i}" for i in range(20)]

    def add(i):
        order = texts if i % 2 else texts[::-1]
        return add_words(studio, categories[i % 4], *order)

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(add, range(8)))
    assert music_db.scalar(select(func.count()).select_from(Word)) == 20
    assert music_db.scalar(select(func.count()).select_from(Link)) == 80

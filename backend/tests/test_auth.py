from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, update

from app import auth
from app.models import LoginCode, Session, User

EMAIL = "player@example.com"


def request_code(client, email=EMAIL):
    response = client.post("/api/auth/code", json={"email": email})
    assert response.status_code == 200, response.text
    return response.json()["challenge"]


def verify(client, challenge, code):
    return client.post("/api/auth/verify", json={"challenge": challenge, "code": code})


def sign_in(client, mailer, email=EMAIL):
    challenge = request_code(client, email)
    response = verify(client, challenge, mailer.sent[-1][2])
    assert response.status_code == 200, response.text
    return response


def wrong(code):
    return f"{(int(code) + 1) % 1_000_000:06}"


def test_sign_in_and_out(music, mailer):
    assert music.get("/api/auth/me").status_code == 401
    response = sign_in(music, mailer, "Player@Example.com")
    assert response.json() == {"email": EMAIL, "display_name": None, "role": "player"}
    assert music.get("/api/auth/me").json()["email"] == EMAIL

    token = music.cookies["__Host-session"]
    assert music.post("/api/auth/logout").status_code == 204
    music.cookies.set("__Host-session", token)
    assert music.get("/api/auth/me").status_code == 401  # revoked on the server too


def test_cookie_is_locked_down(music, mailer):
    cookie = sign_in(music, mailer).headers["set-cookie"].lower()
    assert cookie.startswith("__host-session=")
    for part in ("httponly", "secure", "samesite=lax", "path=/"):
        assert part in cookie
    assert "domain=" not in cookie


def test_secrets_are_not_stored(music, mailer, music_db):
    challenge = request_code(music)
    code = mailer.sent[-1][2]
    row = music_db.scalars(select(LoginCode)).one()
    stored = {row.code_hash, row.challenge_hash, row.ip_hash}
    assert not stored & {code, challenge, "testclient"}
    verify(music, challenge, code)
    assert music_db.scalars(select(Session)).one().token_hash != music.cookies["__Host-session"]


def test_returning_user_keeps_one_account(music, mailer, music_db):
    sign_in(music, mailer)
    sign_in(music, mailer, EMAIL.upper())
    assert music_db.scalar(select(func.count()).select_from(User)) == 1


def test_code_works_once(music, mailer):
    challenge = request_code(music)
    code = mailer.sent[-1][2]
    assert verify(music, challenge, code).status_code == 200
    assert verify(music, challenge, code).status_code == 400


def test_code_needs_its_own_challenge(music, mailer):
    request_code(music, "victim@example.com")
    code = mailer.sent[-1][2]
    other = request_code(music, "attacker@example.com")
    if code != mailer.sent[-1][2]:
        assert verify(music, other, code).status_code == 400
    assert verify(music, "made-up", code).status_code == 400


def test_code_expires(music, mailer, music_db):
    challenge = request_code(music)
    music_db.execute(update(LoginCode).values(expires_at=datetime.now(UTC)))
    music_db.commit()
    assert verify(music, challenge, mailer.sent[-1][2]).status_code == 400


def test_attempt_limit(music, mailer):
    challenge = request_code(music)
    code = mailer.sent[-1][2]
    for _ in range(auth.CODE_MAX_ATTEMPTS):
        assert verify(music, challenge, wrong(code)).status_code == 400
    assert verify(music, challenge, code).status_code == 400


def test_right_code_still_works_after_a_mistake(music, mailer):
    challenge = request_code(music)
    code = mailer.sent[-1][2]
    verify(music, challenge, wrong(code))
    assert verify(music, challenge, code).status_code == 200


def test_parallel_guesses_cannot_exceed_attempt_limit(music, mailer, music_db):
    challenge = request_code(music)
    bad = wrong(mailer.sent[-1][2])
    with ThreadPoolExecutor(10) as pool:
        list(pool.map(lambda _: verify(music, challenge, bad), range(20)))
    assert music_db.scalar(select(LoginCode.attempts)) == auth.CODE_MAX_ATTEMPTS


def test_email_rate_limit(music, mailer):
    for _ in range(auth.MAX_CODES_PER_EMAIL):
        request_code(music)
    assert music.post("/api/auth/code", json={"email": EMAIL.upper()}).status_code == 429
    assert len(mailer.sent) == auth.MAX_CODES_PER_EMAIL
    request_code(music, "someone.else@example.com")


def test_parallel_requests_cannot_exceed_rate_limit(music, mailer):
    def post(_):
        return music.post("/api/auth/code", json={"email": EMAIL}).status_code

    with ThreadPoolExecutor(10) as pool:
        statuses = list(pool.map(post, range(12)))
    assert statuses.count(200) == auth.MAX_CODES_PER_EMAIL


def test_ip_rate_limit(music):
    for i in range(auth.MAX_CODES_PER_IP):
        request_code(music, f"user{i}@example.com")
    assert music.post("/api/auth/code", json={"email": "more@example.com"}).status_code == 429


def test_spoofed_ip_header_is_ignored_unless_configured(music):
    for i in range(auth.MAX_CODES_PER_IP):
        request_code(music, f"user{i}@example.com")
    response = music.post(
        "/api/auth/code", json={"email": "more@example.com"}, headers={"Fly-Client-IP": "1.2.3.4"}
    )
    assert response.status_code == 429


def test_expired_session(music, mailer, music_db):
    sign_in(music, mailer)
    music_db.execute(update(Session).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    music_db.commit()
    assert music.get("/api/auth/me").status_code == 401


def test_mail_failure_is_reported(music, mailer):
    mailer.broken = True
    assert music.post("/api/auth/code", json={"email": EMAIL}).status_code == 503


@pytest.mark.parametrize("email", ["", "nope", "a@b", "x@example.com\nBcc: y@example.com"])
def test_bad_email_rejected(music, mailer, email):
    assert music.post("/api/auth/code", json={"email": email}).status_code == 422
    assert mailer.sent == []


@pytest.mark.parametrize("role,allowed", [("player", 0), ("contributor", 1), ("admin", 1)])
def test_contributor_role_check(role, allowed):
    check = auth.require_role("contributor", "admin")
    user = User(email=EMAIL, role=role)
    if allowed:
        assert check(user) is user
    else:
        with pytest.raises(HTTPException) as e:
            check(user)
        assert e.value.status_code == 403

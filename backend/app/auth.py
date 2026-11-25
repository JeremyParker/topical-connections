import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from .config import Settings, Topic
from .mailer import MailError
from .models import LoginCode, Session, User
from .topics import CurrentTopic, Db

CODE_TTL = timedelta(minutes=10)
CODE_MAX_ATTEMPTS = 5
SESSION_TTL = timedelta(days=90)
RATE_WINDOW = timedelta(hours=1)
MAX_CODES_PER_EMAIL = 5
MAX_CODES_PER_IP = 20

log = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/{topic_slug}/auth", tags=["auth"])


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


AppSettings = Annotated[Settings, Depends(get_app_settings)]


def keyed_hash(settings: Settings, *parts: str) -> str:
    message = "\0".join(parts).encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def cookie_name(settings: Settings, topic: Topic) -> str:
    # Named by topic, so that topics sharing a host don't share a session.
    # Browsers force __Host- cookies to be Secure and limited to this exact host.
    return f"{'__Host-' if settings.is_production else ''}session-{topic.slug}"


def client_ip(request: Request, settings: Settings) -> str:
    if settings.client_ip_header:
        if ip := request.headers.get(settings.client_ip_header):
            return ip
    return request.client.host if request.client else "unknown"


class CodeRequest(BaseModel):
    email: EmailStr


class CodeChallenge(BaseModel):
    challenge: str


class CodeVerification(BaseModel):
    challenge: str = Field(max_length=100)
    code: str = Field(pattern=r"^[0-9]{6}$")


class UserOut(BaseModel):
    email: str
    display_name: str | None
    role: str


@router.post("/code")
def request_code(
    body: CodeRequest, request: Request, topic: CurrentTopic, db: Db, settings: AppSettings
) -> CodeChallenge:
    """Emails a code. Accounts are created on first sign-in, so the response
    can't reveal whether one already exists."""
    email = body.email.strip().lower()
    ip_hash = keyed_hash(settings, topic.slug, "ip", client_ip(request, settings))
    now = datetime.now(UTC)

    # Serialize requests from the same email or IP, so they can't race past the
    # limits. Locks are taken in a consistent order to avoid deadlock.
    for key in sorted([f"email:{email}", f"ip:{ip_hash}"]):
        db.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(key, 0))))
    db.execute(delete(LoginCode).where(LoginCode.created_at < now - timedelta(days=1)))
    for column, value, limit in (
        (LoginCode.email, email, MAX_CODES_PER_EMAIL),
        (LoginCode.ip_hash, ip_hash, MAX_CODES_PER_IP),
    ):
        count = db.scalar(
            select(func.count())
            .select_from(LoginCode)
            .where(column == value, LoginCode.created_at > now - RATE_WINDOW)
        )
        if count >= limit:
            raise HTTPException(429, "Too many codes requested. Please try again later.")

    challenge = secrets.token_urlsafe(32)
    code = f"{secrets.randbelow(1_000_000):06}"
    db.add(
        LoginCode(
            email=email,
            challenge_hash=keyed_hash(settings, topic.slug, "challenge", challenge),
            code_hash=keyed_hash(settings, topic.slug, "code", challenge, code),
            ip_hash=ip_hash,
            expires_at=now + CODE_TTL,
        )
    )
    db.commit()

    try:
        request.app.state.mailer.send_login_code(topic, email, code)
    except MailError as e:
        log.error("could not send a login code: %s", e)
        raise HTTPException(503, "We couldn't send your code. Please try again.") from e
    return CodeChallenge(challenge=challenge)


@router.post("/verify")
def verify_code(
    body: CodeVerification, response: Response, topic: CurrentTopic, db: Db, settings: AppSettings
) -> UserOut:
    now = datetime.now(UTC)
    failure = HTTPException(400, "That code is wrong or has expired.")

    # Locked so that parallel guesses can't exceed the attempt limit.
    login = db.scalar(
        select(LoginCode)
        .where(
            LoginCode.challenge_hash
            == keyed_hash(settings, topic.slug, "challenge", body.challenge)
        )
        .with_for_update()
    )
    if (
        login is None
        or login.used_at is not None
        or login.expires_at <= now
        or login.attempts >= CODE_MAX_ATTEMPTS
    ):
        raise failure

    expected = keyed_hash(settings, topic.slug, "code", body.challenge, body.code)
    if not hmac.compare_digest(login.code_hash, expected):
        login.attempts += 1
        db.commit()
        raise failure

    login.used_at = now
    db.execute(insert(User).values(email=login.email).on_conflict_do_nothing())
    user = db.scalars(select(User).where(User.email == login.email)).one()

    token = secrets.token_urlsafe(32)
    db.execute(delete(Session).where(Session.expires_at <= now))
    db.add(
        Session(
            user_id=user.id,
            token_hash=keyed_hash(settings, topic.slug, "session", token),
            expires_at=now + SESSION_TTL,
        )
    )
    db.commit()

    response.set_cookie(
        cookie_name(settings, topic),
        token,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )
    return UserOut.model_validate(user, from_attributes=True)


def session_hash(request: Request, topic: CurrentTopic, settings: AppSettings) -> str | None:
    token = request.cookies.get(cookie_name(settings, topic))
    return keyed_hash(settings, topic.slug, "session", token) if token else None


SessionHash = Annotated[str | None, Depends(session_hash)]


def current_user(token_hash: SessionHash, db: Db) -> User:
    user = token_hash and db.scalar(
        select(User)
        .join(Session, Session.user_id == User.id)
        .where(Session.token_hash == token_hash, Session.expires_at > datetime.now(UTC))
    )
    if not user:
        raise HTTPException(401, "Not signed in")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_role(*roles: str):
    def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Not allowed")
        return user

    return check


# For the content studio endpoints.
Contributor = Annotated[User, Depends(require_role("contributor", "admin"))]


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    token_hash: SessionHash,
    topic: CurrentTopic,
    db: Db,
    settings: AppSettings,
) -> None:
    if token_hash:
        db.execute(delete(Session).where(Session.token_hash == token_hash))
        db.commit()
    response.delete_cookie(
        cookie_name(settings, topic),
        path="/",
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
    )

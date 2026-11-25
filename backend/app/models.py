from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ROLES = ("player", "contributor", "admin")


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_N_name)s",
            "pk": "pk_%(table_name)s",
        }
    )
    type_annotation_map = {
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[Any]: JSONB,
    }


class Created:
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# --- accounts ---


class User(Created, Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('player', 'contributor', 'admin')", name="role"),)

    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lowercase
    display_name: Mapped[str | None] = mapped_column(String(50))  # shown in game credits
    role: Mapped[str] = mapped_column(String(20), server_default="player")


class LoginCode(Created, Base):
    __tablename__ = "login_codes"

    email: Mapped[str] = mapped_column(String(320), index=True)
    challenge_hash: Mapped[str] = mapped_column(String(64), unique=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    attempts: Mapped[int] = mapped_column(server_default="0")
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class Session(Created, Base):
    __tablename__ = "sessions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime]


# --- word graph ---


class Word(Created, Base):
    __tablename__ = "words"
    __table_args__ = (
        Index(
            "uq_words_text_live",
            text("lower(text)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    text: Mapped[str] = mapped_column(String(50))  # keeps its original capitalization
    deleted_at: Mapped[datetime | None]


class Category(Created, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint("difficulty BETWEEN 0 AND 3", name="difficulty"),
        Index(
            "uq_categories_name_live",
            text("lower(name)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(256))
    notes: Mapped[str | None]
    difficulty: Mapped[int]
    # Whether a word is topical is derived: it has a link to a topical category.
    is_topical: Mapped[bool]
    deleted_at: Mapped[datetime | None]


class Link(Created, Base):
    """One meaning of a word: its membership of a category."""

    __tablename__ = "links"
    __table_args__ = (
        CheckConstraint("difficulty_override BETWEEN 0 AND 3", name="difficulty_override"),
        # Lets game_entries guarantee that its three ids agree.
        UniqueConstraint("id", "word_id", "category_id"),
        Index(
            "uq_links_word_category_live",
            "word_id",
            "category_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    word_id: Mapped[int] = mapped_column(ForeignKey("words.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    difficulty_override: Mapped[int | None]
    example_sentence: Mapped[str | None]
    deleted_at: Mapped[datetime | None]


class Contribution(Created, Base):
    """Append-only record of who did what to the word graph."""

    __tablename__ = "contributions"
    __table_args__ = (
        CheckConstraint("entity_type IN ('word', 'category', 'link')", name="entity_type"),
        CheckConstraint("action IN ('create', 'update', 'delete', 'restore')", name="action"),
        Index(None, "entity_type", "entity_id"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[int]
    details: Mapped[dict[str, Any] | None]


# --- games ---


class Job(Created, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name="status"),
    )

    kind: Mapped[str] = mapped_column(String(50))
    params: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(20), server_default="queued", index=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    error: Mapped[str | None]
    finished_at: Mapped[datetime | None]


class Candidate(Created, Base):
    __tablename__ = "candidates"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="status"),
    )

    game: Mapped[dict[str, Any]]
    score: Mapped[float]
    status: Mapped[str] = mapped_column(String(20), server_default="pending", index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))


class Review(Created, Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("verdict IN ('approve', 'reject')", name="verdict"),
        UniqueConstraint("candidate_id", "user_id"),
    )

    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    verdict: Mapped[str] = mapped_column(String(20))
    feedback: Mapped[str | None]


class PublishedGame(Created, Base):
    """An approved game. It is queued but unscheduled while serve_date is null."""

    __tablename__ = "published_games"

    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("candidates.id"), unique=True)
    serve_date: Mapped[date | None] = mapped_column(unique=True)
    snapshot: Mapped[dict[str, Any]]  # full copy, so later edits can't change the game


class GameEntry(Base):
    """Usage history: which meaning of each word a game used."""

    __tablename__ = "game_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["link_id", "word_id", "category_id"],
            ["links.id", "links.word_id", "links.category_id"],
        ),
        Index(None, "word_id", "category_id"),
        Index(None, "category_id"),
    )

    game_id: Mapped[int] = mapped_column(
        ForeignKey("published_games.id", ondelete="CASCADE"), primary_key=True
    )
    word_id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int]
    link_id: Mapped[int]


class Play(Created, Base):
    __tablename__ = "plays"
    __table_args__ = (UniqueConstraint("user_id", "game_id"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    game_id: Mapped[int] = mapped_column(ForeignKey("published_games.id"), index=True)
    guesses: Mapped[list[Any]]
    won: Mapped[bool]
    mistakes: Mapped[int]

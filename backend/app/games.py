"""Generating candidate games, and listing them for contributors."""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from generator import graph as g
from generator.generate import generate, to_json
from generator.history import History, Use
from generator.suggest import suggest

from .auth import Contributor, require_role
from .models import Candidate, Category, GameEntry, Job, Link, PublishedGame, Word
from .studio import Id
from .topics import Db, TopicRuntime, get_runtime

MAX_CANDIDATES = 20
# Generation takes seconds, so a job this old was lost to a restart.
JOB_TIMEOUT = timedelta(minutes=2)
JOB_LOCK = 4445

log = logging.getLogger("uvicorn.error")
router = APIRouter(
    prefix="/api/{topic_slug}/studio",
    tags=["games"],
    dependencies=[Depends(require_role("contributor", "admin"))],
)


class GenerateIn(BaseModel):
    count: int = Field(default=10, ge=1, le=MAX_CANDIDATES)


class JobOut(BaseModel):
    id: int
    status: str
    created_at: datetime
    result: dict[str, Any] | None
    error: str | None


class CandidateOut(BaseModel):
    id: int
    score: float
    status: str
    created_at: datetime
    game: dict[str, Any]


class CandidatePage(BaseModel):
    total: int
    items: list[CandidateOut]


class CategoryLink(BaseModel):
    id: int
    name: str


class SuggestionsOut(BaseModel):
    almost_usable: list[CategoryLink]
    isolated: list[CategoryLink]


def load_graph(db: DbSession) -> g.Graph:
    words = db.execute(select(Word.id, Word.text).where(Word.deleted_at.is_(None)))
    categories = db.execute(
        select(Category.id, Category.name, Category.difficulty, Category.is_topical).where(
            Category.deleted_at.is_(None)
        )
    )
    words = {row.id: row.text for row in words}
    categories = {row.id: g.Category(*row) for row in categories}
    links = db.execute(
        select(Link.id, Link.word_id, Link.category_id, Link.difficulty_override)
        .where(Link.deleted_at.is_(None))
        .order_by(Link.id)
    )
    # An edit may land between these queries, so skip links to anything not loaded
    return g.Graph(
        words,
        categories,
        [g.Link(*x) for x in links if x.word_id in words and x.category_id in categories],
    )


def next_free_date(db: DbSession, today: date) -> date:
    taken = set(
        db.scalars(select(PublishedGame.serve_date).where(PublishedGame.serve_date > today))
    )
    day = today + timedelta(days=1)
    while day in taken:
        day += timedelta(days=1)
    return day


def load_history(db: DbSession, on: date) -> History:
    rows = db.execute(
        select(GameEntry.word_id, GameEntry.category_id, PublishedGame.serve_date).join(
            PublishedGame, PublishedGame.id == GameEntry.game_id
        )
    )
    return History((Use(*row) for row in rows), on)


def word_ids(game: dict[str, Any]) -> frozenset[int]:
    return frozenset(w["word_id"] for group in game["groups"] for w in group["words"])


def run_generation(sessions: sessionmaker[DbSession], job_id: int) -> None:
    try:
        with sessions() as db:
            job = db.get_one(Job, job_id)
            job.status = "running"
            count = job.params["count"]
            db.commit()

            graph = load_graph(db)
            history = load_history(db, next_free_date(db, datetime.now(UTC).date()))
            avoid = {word_ids(game) for game in db.scalars(select(Candidate.game))}
            # Don't hold a connection while computing
            db.rollback()

            result = generate(graph, history, count, avoid=avoid)

            job = db.get_one(Job, job_id, with_for_update=True, populate_existing=True)
            if job.status != "running":
                return  # it timed out
            for game in result.games:
                db.add(Candidate(game=to_json(graph, game), score=game.score, job_id=job_id))
            job.status = "done"
            job.result = {
                "created": len(result.games),
                "problem": result.problem,
                "stats": result.stats,
            }
            job.finished_at = func.now()
            db.commit()
    except Exception:
        log.exception("generation job %s failed", job_id)
        with sessions() as db:
            db.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(status="failed", error="Something went wrong.", finished_at=func.now())
            )
            db.commit()


@router.post("/jobs", status_code=202)
def start_generation(
    body: GenerateIn,
    tasks: BackgroundTasks,
    runtime: Annotated[TopicRuntime, Depends(get_runtime)],
    db: Db,
    user: Contributor,
) -> JobOut:
    db.execute(select(func.pg_advisory_xact_lock(JOB_LOCK)))
    active = Job.status.in_(("queued", "running"))
    db.execute(
        update(Job)
        .where(active, Job.created_at < func.now() - JOB_TIMEOUT)
        .values(status="failed", error="The job was interrupted.", finished_at=func.now())
    )
    if db.scalar(select(Job.id).where(active).limit(1)):
        db.commit()
        raise HTTPException(409, "Games are already being generated.")
    job = Job(kind="generate", params={"count": body.count}, requested_by=user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    out = JobOut.model_validate(job, from_attributes=True)
    tasks.add_task(run_generation, runtime.sessions, job.id)
    return out


@router.get("/jobs/{job_id}")
def get_job(job_id: Id, db: Db) -> JobOut:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "That job doesn't exist.")
    out = JobOut.model_validate(job, from_attributes=True)
    if job.status in ("queued", "running") and job.created_at < datetime.now(UTC) - JOB_TIMEOUT:
        out.status = "failed"
        out.error = "The job was interrupted."
    return out


@router.get("/candidates")
def list_candidates(
    db: Db,
    status: Literal["pending", "approved", "rejected"] = "pending",
    offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
) -> CandidatePage:
    where = Candidate.status == status
    rows = db.scalars(
        select(Candidate)
        .where(where)
        .order_by(Candidate.score.desc(), Candidate.id)
        .offset(offset)
        .limit(50)
    )
    return CandidatePage(
        total=db.scalar(select(func.count()).select_from(Candidate).where(where)),
        items=[CandidateOut.model_validate(c, from_attributes=True) for c in rows],
    )


@router.get("/suggestions")
def suggestions(db: Db) -> SuggestionsOut:
    graph = load_graph(db)
    found = suggest(graph)

    def named(ids: list[int]) -> list[CategoryLink]:
        return [CategoryLink(id=c, name=graph.categories[c].name) for c in ids[:10]]

    return SuggestionsOut(almost_usable=named(found.almost_usable), isolated=named(found.isolated))

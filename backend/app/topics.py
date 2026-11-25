from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import sessionmaker

from .config import Topic


@dataclass(frozen=True)
class TopicRuntime:
    topic: Topic
    engine: Engine
    sessions: sessionmaker[DbSession]


class TopicRegistry:
    """Finds a topic, and so its database, from a request's hostname."""

    def __init__(self, topics: list[Topic]):
        self._by_host: dict[str, TopicRuntime] = {}
        self.runtimes: list[TopicRuntime] = []
        for topic in topics:
            # pre_ping because the database may have gone to sleep since last use
            engine = create_engine(
                topic.database_url, pool_pre_ping=True, pool_size=2, max_overflow=3
            )
            runtime = TopicRuntime(topic, engine, sessionmaker(engine, expire_on_commit=False))
            self.runtimes.append(runtime)
            for host in topic.hosts:
                self._by_host[host] = runtime

    def for_host(self, host: str | None) -> TopicRuntime | None:
        return self._by_host.get((host or "").lower())

    def dispose(self) -> None:
        for runtime in self.runtimes:
            runtime.engine.dispose()


def get_runtime(request: Request) -> TopicRuntime:
    runtime = request.app.state.topics.for_host(request.url.hostname)
    if runtime is None:
        raise HTTPException(404, "Not found")
    # CORS allows the origins of every topic, so check this topic's here.
    origin = request.headers.get("origin")
    if origin is not None and origin not in runtime.topic.origins:
        raise HTTPException(403, "Origin not allowed")
    return runtime


def get_topic(runtime: Annotated[TopicRuntime, Depends(get_runtime)]) -> Topic:
    return runtime.topic


def get_db(runtime: Annotated[TopicRuntime, Depends(get_runtime)]) -> Iterator[DbSession]:
    with runtime.sessions() as db:
        yield db


CurrentTopic = Annotated[Topic, Depends(get_topic)]
Db = Annotated[DbSession, Depends(get_db)]

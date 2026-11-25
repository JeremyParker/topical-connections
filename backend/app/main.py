from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import auth, games, studio
from .config import Settings, get_settings, load_topics
from .mailer import Mailer, make_mailer
from .topics import CurrentTopic, TopicRegistry


class TopicOut(BaseModel):
    name: str
    topical_label: str


def create_app(settings: Settings | None = None, mailer: Mailer | None = None) -> FastAPI:
    settings = settings or get_settings()
    registry = TopicRegistry(load_topics(settings))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        registry.dispose()

    app = FastAPI(
        title="topical-connections",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.topics = registry
    app.state.mailer = mailer or make_mailer(settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted({o for r in registry.runtimes for o in r.topic.origins}),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(auth.router)
    app.include_router(studio.router)
    app.include_router(games.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        # Doesn't touch a database, so health checks won't keep one awake.
        return {"status": "ok"}

    @app.get("/api/{topic_slug}/topic")
    def topic(topic: CurrentTopic) -> TopicOut:
        return TopicOut(name=topic.name, topical_label=topic.topical_label)

    return app

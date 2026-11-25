"""Tests run against real Postgres, with two topics, each in its own database."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, make_url, text

from app import cli
from app.config import Settings, load_topics
from app.mailer import MailError
from app.main import create_app
from app.models import Base

SERVER_URL = make_url(
    os.environ.get("TEST_SERVER_URL", "postgresql+psycopg://dev:dev@localhost:5433/postgres")
)
SLUGS = ("music", "biology")


class FakeMailer:
    def __init__(self):
        self.sent = []
        self.broken = False

    def send_login_code(self, topic, to, code):
        if self.broken:
            raise MailError("broken")
        self.sent.append((topic.slug, to, code))


@pytest.fixture(scope="session")
def settings(tmp_path_factory):
    admin = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        for slug in SLUGS:
            c.execute(text(f"DROP DATABASE IF EXISTS test_{slug} WITH (FORCE)"))
            c.execute(text(f"CREATE DATABASE test_{slug}"))

    toml = ""
    for slug in SLUGS:
        url = SERVER_URL.set(database=f"test_{slug}").render_as_string(hide_password=False)
        os.environ[f"TEST_DATABASE_URL_{slug.upper()}"] = url
        toml += f"""
[{slug}]
name = "{slug} game"
topical_label = "is about {slug}"
email_from = "login@{slug}.test"
database_url_env = "TEST_DATABASE_URL_{slug.upper()}"
hosts = ["api.{slug}.test"]
origins = ["https://{slug}.test"]
"""
    path = tmp_path_factory.mktemp("config") / "topics.toml"
    path.write_text(toml)
    settings = Settings(
        _env_file=None,
        environment="production",
        secret_key="test-secret-" * 4,
        email_backend="resend",
        resend_api_key="unused",
        topics_file=path,
        enabled_topics="",
        client_ip_header="",
    )
    for topic in load_topics(settings):
        cli.migrate(topic)
    yield settings
    with admin.connect() as c:
        for slug in SLUGS:
            c.execute(text(f"DROP DATABASE test_{slug} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def mailer():
    return FakeMailer()


@pytest.fixture
def app(settings, mailer):
    app = create_app(settings, mailer)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    for runtime in app.state.topics.runtimes:
        with runtime.engine.begin() as c:
            c.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield app
    app.state.topics.dispose()


@pytest.fixture
def music(app):
    return TestClient(app, base_url="https://api.music.test")


@pytest.fixture
def biology(app):
    return TestClient(app, base_url="https://api.biology.test")


@pytest.fixture
def music_db(app):
    with app.state.topics.for_host("api.music.test").sessions() as db:
        yield db


@pytest.fixture
def biology_db(app):
    with app.state.topics.for_host("api.biology.test").sessions() as db:
        yield db

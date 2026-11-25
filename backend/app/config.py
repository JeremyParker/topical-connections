import os
import re
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

BACKEND_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    environment: Literal["development", "production"] = "production"
    secret_key: str = Field(min_length=32)
    email_backend: Literal["console", "resend"] = "resend"
    resend_api_key: str = ""
    topics_file: Path = BACKEND_DIR / "topics.toml"
    # Comma-separated slugs. Empty means every topic, so a topic can be split
    # into its own deployment by setting this.
    enabled_topics: str = ""
    # Header holding the real client IP, set only behind a proxy that overwrites
    # it (e.g. Fly-Client-IP). Otherwise clients could spoof their address.
    client_ip_header: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def check_email(self):
        if self.is_production and self.email_backend == "console":
            raise ValueError("EMAIL_BACKEND=console would write login codes to production logs")
        if self.email_backend == "resend" and not self.resend_api_key:
            raise ValueError("EMAIL_BACKEND=resend needs RESEND_API_KEY")
        return self


@dataclass(frozen=True)
class Topic:
    slug: str
    name: str
    topical_label: str
    email_from: str
    database_url: str
    origins: tuple[str, ...]


def load_topics(settings: Settings) -> list[Topic]:
    raw = tomllib.loads(settings.topics_file.read_text())
    enabled = {s.strip() for s in settings.enabled_topics.split(",") if s.strip()} or set(raw)
    if unknown := enabled - set(raw):
        raise ValueError(f"ENABLED_TOPICS has unknown topics: {sorted(unknown)}")

    # Slugs appear in URLs and cookie names
    if bad := [slug for slug in raw if not re.fullmatch(r"[a-z0-9-]+", slug)]:
        raise ValueError(f"Invalid topic slugs: {bad}")

    topics = []
    for slug in sorted(enabled):
        entry = raw[slug]
        env_name = entry["database_url_env"]
        url = os.environ.get(env_name)
        if not url:
            raise ValueError(f"Topic {slug!r} needs the environment variable {env_name}")
        # Hosts hand out plain URLs; SQLAlchemy needs the driver named.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                url = "postgresql+psycopg://" + url.removeprefix(prefix)
        topics.append(
            Topic(
                slug=slug,
                name=entry["name"],
                topical_label=entry["topical_label"],
                email_from=entry["email_from"],
                database_url=url,
                origins=tuple(entry["origins"]),
            )
        )

    urls = [t.database_url for t in topics]
    if len(urls) != len(set(urls)):
        raise ValueError("Two topics share a database")
    return topics


@lru_cache
def get_settings() -> Settings:
    load_dotenv(BACKEND_DIR / ".env")
    return Settings()

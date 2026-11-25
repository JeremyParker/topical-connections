"""Admin commands: python -m app.cli --help"""

import argparse

from alembic import command
from alembic.config import Config
from email_validator import validate_email
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from .config import BACKEND_DIR, Topic, get_settings, load_topics
from .models import ROLES, User


def alembic_config(database_url: str) -> Config:
    config = Config(BACKEND_DIR / "alembic.ini")
    config.attributes["database_url"] = database_url
    return config


def migrate(topic: Topic) -> None:
    print(f"Migrating {topic.slug}")
    command.upgrade(alembic_config(topic.database_url), "head")


def set_role(topic: Topic, email: str, role: str) -> None:
    email = validate_email(email, check_deliverability=False).normalized.lower()
    engine = create_engine(topic.database_url)
    with DbSession(engine) as db:
        db.execute(
            insert(User)
            .values(email=email, role=role)
            .on_conflict_do_update(index_elements=[User.email], set_={"role": role})
        )
        db.commit()
    engine.dispose()
    print(f"{email} is now {role} in {topic.slug}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("migrate", help="bring topic databases up to date")
    p.add_argument("--topic", help="only this topic (default: all)")

    p = sub.add_parser("makemigration", help="generate a migration from model changes")
    p.add_argument("message")

    p = sub.add_parser("set-role", help="invite or change a user, creating them if needed")
    p.add_argument("topic")
    p.add_argument("email")
    p.add_argument("role", choices=ROLES)

    args = parser.parse_args()
    topics = {t.slug: t for t in load_topics(get_settings())}
    slug = getattr(args, "topic", None)
    if slug and slug not in topics:
        parser.error(f"unknown topic {slug!r}; choose from {', '.join(topics)}")

    if args.command == "migrate":
        for topic in [topics[slug]] if slug else topics.values():
            migrate(topic)
    elif args.command == "makemigration":
        # Every topic has the same schema, so compare against any one of them.
        config = alembic_config(next(iter(topics.values())).database_url)
        command.revision(config, message=args.message, autogenerate=True)
    elif args.command == "set-role":
        set_role(topics[slug], args.email, args.role)


if __name__ == "__main__":
    main()

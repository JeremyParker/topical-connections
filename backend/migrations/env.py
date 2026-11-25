from alembic import context
from sqlalchemy import create_engine, pool

from app.models import Base

url = context.config.attributes.get("database_url")
if not url:
    raise SystemExit("Use `python -m app.cli migrate` or `makemigration`.")

engine = create_engine(url, poolclass=pool.NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()

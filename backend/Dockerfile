FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.21 /uv /bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-cache
COPY alembic.ini topics.toml ./
COPY migrations migrations/
COPY app app/
ENV PATH="/srv/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
USER nobody
EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

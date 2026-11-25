# topical-connections

A daily word-matching game with a separate version for each topic. The first is
FourFour, about music. See [plan.txt](plan.txt) for the design.

## Run locally

Needs Docker, [uv](https://docs.astral.sh/uv/) and Node 22.

    docker compose up -d
    cd backend
    cp .env.example .env
    uv run python -m app.cli migrate
    uv run uvicorn app.main:create_app --factory --reload

In another terminal:

    cd frontend
    npm install
    npm run dev

Open http://localhost:5173. Login codes are printed in the backend's output.

To give someone access to the studio (this also invites new users):

    uv run python -m app.cli set-role music you@example.com admin

## Test

    cd backend && uv run pytest && uv run ruff check .
    cd frontend && VITE_TOPIC=music npm run build

Tests create and drop their own databases, `test_music` and `test_biology`.

## Change the schema

Edit `backend/app/models.py`, then, with your local database migrated:

    uv run python -m app.cli makemigration "what changed"
    uv run python -m app.cli migrate

Read the generated file before committing it.

## Add a topic

1. Create an empty database.
2. Add an entry to `backend/topics.toml`, and set its database URL variable.
3. Run `python -m app.cli migrate --topic <slug>`.
4. Build the frontend with `VITE_TOPIC=<slug>`, and `VITE_API_BASE` set to an API
   address on the topic's own domain. Otherwise browsers may block its cookies.

The slug in each URL (`/api/<slug>/...`) selects the topic, and so the database.
The API address doesn't, so all topics' API addresses can point to one server.

To deploy a topic on its own, set `ENABLED_TOPICS=<slug>`.

## Production settings

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | At least 32 random characters. Changing it signs everyone out. |
| `RESEND_API_KEY` | Sends login codes |
| `DATABASE_URL_<TOPIC>` | One per topic |
| `ENABLED_TOPICS` | Optional, comma-separated |
| `CLIENT_IP_HEADER` | The header in which the proxy puts the real client IP, such as `Fly-Client-IP`. Without it, everyone behind the proxy shares one rate limit. Only set a header the proxy always overwrites. |

Migrations don't run on startup. Run `python -m app.cli migrate` as a release step.

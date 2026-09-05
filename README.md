# ORCA Backend

Marine Ecosystem Reasoning with Collaborative Agents — SIH 2026 (SIH26176).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Configuration

Copy `.env.example` to `.env` and adjust values. Set `DATABASE_URL` to your PostgreSQL+PostGIS connection (e.g. `postgresql+asyncpg://user:password@localhost:5432/orca`). The API/ping foundation can run on SQLite, but the schema and Alembic migrations target PostgreSQL+PostGIS.

### AI / Chat Environment Variables

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | _(empty)_ | Groq API key for LLM-based agents. If absent, LLM-dependent features degrade gracefully. |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Groq model identifier used by chat agents. |
| `CHAT_TIMEOUT_SECONDS` | `8.0` | Maximum execution time per agent attempt. |
| `CHAT_MAX_RETRIES` | `2` | Maximum retry count per agent on transient failures. |
| `CACHE_STALE_THRESHOLD_SECONDS` | `3600` | Threshold for considering a cached data source stale. |

## Run

```bash
uvicorn app.main:app --reload
```

## Tests

```bash
pytest
```

## Status

Milestone 1 — Project Foundation: COMPLETE.
Milestone 2 — Database Infrastructure & Core Models: COMPLETE (requires PostgreSQL+PostGIS to apply migrations).
Milestone 3 — AI Foundation: COMPLETE.

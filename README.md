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

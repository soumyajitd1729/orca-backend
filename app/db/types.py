from app.config import settings
from sqlalchemy import JSON, String


def _is_sqlite() -> bool:
    # Local development uses SQLite; production uses PostgreSQL+PostGIS.
    return settings.DATABASE_URL.startswith("sqlite")


def jsonb():
    # PostgreSQL: native JSONB (matches Alembic migration).
    # SQLite (local dev): JSON stored as TEXT.
    if _is_sqlite():
        return JSON()
    from sqlalchemy.dialects.postgresql import JSONB

    return JSONB()


def geometry(geometry_type: str, srid: int = 4326):
    # PostgreSQL: real PostGIS geometry (matches Alembic migration).
    # SQLite (local dev): plain TEXT column (no spatial queries offline).
    if _is_sqlite():
        return String()
    from geoalchemy2 import Geometry

    return Geometry(geometry_type=geometry_type, srid=srid)

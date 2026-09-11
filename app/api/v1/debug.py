from fastapi import APIRouter
from sqlalchemy.engine import make_url

from app.config import settings
from app.repositories.pfz_repository import _is_postgres

router = APIRouter()


@router.get("/debug/pfz-status")
async def pfz_debug_status():
    database_url = settings.DATABASE_URL
    parsed = make_url(database_url)
    return {
        "is_postgresql": _is_postgres(),
        "database_host": parsed.host or None,
        "database_port": parsed.port or None,
        "database_name": parsed.database or None,
        "app_version": "0.1.0",
    }

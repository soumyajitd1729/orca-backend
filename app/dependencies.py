from app.config import settings
from fastapi import Depends
from app.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession


def get_settings():
    return settings


def get_db_session() -> AsyncSession:
    return get_db()

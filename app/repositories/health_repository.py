from datetime import datetime
from typing import Optional

from app.db.session import AsyncSession
from app.models.data_source_health import DataSourceHealth
from app.models.enums import SourceStatus
from sqlalchemy import select


async def get_all_sources(db: AsyncSession) -> list[DataSourceHealth]:
    result = await db.execute(select(DataSourceHealth))
    return list(result.scalars().all())


async def get_source_by_name(db: AsyncSession, name: str) -> Optional[DataSourceHealth]:
    result = await db.execute(select(DataSourceHealth).where(DataSourceHealth.name == name))
    return result.scalar_one_or_none()


async def update_source_status(
    db: AsyncSession, name: str, status: SourceStatus, last_fetch_at: Optional[datetime] = None
) -> Optional[DataSourceHealth]:
    source = await get_source_by_name(db, name)
    if source is None:
        return None
    source.status = status
    if last_fetch_at is not None:
        source.last_fetch_at = last_fetch_at
    await db.commit()
    await db.refresh(source)
    return source

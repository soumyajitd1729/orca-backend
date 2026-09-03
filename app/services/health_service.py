from datetime import datetime
from typing import Optional

from app.models.data_source_health import DataSourceHealth
from app.models.enums import SourceStatus
from app.repositories import health_repository
from app.schemas.health import HealthData, SourceDetail, SourceHealth

SOURCE_KEYS = ("incois", "mosdac", "imd")


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _to_source(row: Optional[DataSourceHealth]) -> SourceHealth:
    if row is None:
        return SourceHealth(status="unavailable", last_success_at=None)
    last: Optional[str] = row.last_fetch_at.isoformat() if row.last_fetch_at else None
    return SourceHealth(status=_status_value(row.status), last_success_at=last)


def _to_source_detail(row: DataSourceHealth) -> SourceDetail:
    return SourceDetail(
        name=row.name,
        priority=row.priority,
        status=_status_value(row.status),
        last_fetch_at=row.last_fetch_at.isoformat() if row.last_fetch_at else None,
        created_at=row.created_at.isoformat() if row.created_at else None,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


async def get_health_summary(db) -> HealthData:
    rows = await health_repository.get_all_sources(db)
    by_name = {row.name: row for row in rows}
    return HealthData(
        **{key: _to_source(by_name.get(key)) for key in SOURCE_KEYS}
    )


async def get_all_source_details(db) -> list[SourceDetail]:
    rows = await health_repository.get_all_sources(db)
    return [_to_source_detail(row) for row in rows]


async def get_source_detail(db, source_name: str) -> Optional[SourceDetail]:
    row = await health_repository.get_source_by_name(db, source_name)
    if row is None:
        return None
    return _to_source_detail(row)


async def update_source_status(
    db, source_name: str, status: SourceStatus, last_fetch_at: Optional[datetime] = None
) -> Optional[SourceDetail]:
    row = await health_repository.update_source_status(db, source_name, status, last_fetch_at)
    if row is None:
        return None
    return _to_source_detail(row)

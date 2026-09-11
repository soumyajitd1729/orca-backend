from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.models.pfz_zone import PFZZone
from app.repositories.pfz_repository import _is_postgres
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_DWithin, ST_MakePoint, ST_SetSRID

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


@router.get("/debug/pfz-db-status")
async def pfz_db_status(db: AsyncSession = Depends(get_db)):
    database_url = settings.DATABASE_URL
    parsed = make_url(database_url)

    total_rows = 0
    geometry_rows = 0
    nearby_count = 0
    sample_nearby = []
    error = None

    try:
        total_rows = (await db.execute(select(func.count()).select_from(PFZZone))).scalar() or 0
        geometry_rows = (
            await db.execute(select(func.count()).select_from(PFZZone).where(PFZZone.geometry.is_not(None)))
        ).scalar() or 0

        if _is_postgres():
            point = func.ST_SetSRID(func.ST_MakePoint(82.24, 16.94), 4326).cast(Geography)
            nearby_count = (
                await db.execute(
                    select(func.count())
                    .select_from(PFZZone)
                    .where(
                        PFZZone.geometry.is_not(None),
                        ST_DWithin(PFZZone.geometry.cast(Geography), point, 50000),
                    )
                )
            ).scalar() or 0

            nearby_stmt = (
                select(PFZZone)
                .where(
                    PFZZone.geometry.is_not(None),
                    ST_DWithin(PFZZone.geometry.cast(Geography), point, 50000),
                )
                .limit(3)
            )
            result = await db.execute(nearby_stmt)
            for row in result.scalars().all():
                components = row.components or {}
                sample_nearby.append(
                    {
                        "id": str(row.id),
                        "latitude": components.get("latitude"),
                        "longitude": components.get("longitude"),
                        "pfz_probability": components.get("pfz_probability"),
                        "pfz_class": components.get("pfz_class"),
                    }
                )
    except Exception as exc:  # pragma: no cover - diagnostic only
        error = str(exc)

    return {
        "is_postgresql": _is_postgres(),
        "database_host": parsed.host or None,
        "database_name": parsed.database or None,
        "total_pfz_rows": total_rows,
        "geometry_rows": geometry_rows,
        "nearby_50km_count": nearby_count,
        "sample_nearby_rows": sample_nearby,
        "error": error,
    }

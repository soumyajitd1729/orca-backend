import json
from typing import Any, Optional

from app.config import settings
from app.db.session import AsyncSession
from app.models.pfz_zone import PFZZone
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_AsGeoJSON, ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import func, select


def _is_postgres() -> bool:
    return "postgresql" in settings.DATABASE_URL


def _serialize_geometry(geom: Any, geojson_str: Optional[str]) -> Optional[Any]:
    if geojson_str is not None:
        try:
            return json.loads(geojson_str)
        except Exception:
            return geojson_str
    if geom is None:
        return None
    return str(geom)


async def get_pfz_zones_within_radius(
    db: AsyncSession, lat: float, lon: float, radius_km: float
) -> list[tuple[PFZZone, Optional[str]]]:
    if _is_postgres():
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326).cast(Geography)
        stmt = (
            select(PFZZone, ST_AsGeoJSON(PFZZone.geometry).label("geometry_geojson"))
            .where(ST_DWithin(PFZZone.geometry.cast(Geography), point, radius_km * 1000))
            .order_by(PFZZone.valid_time.desc())
        )
        result = await db.execute(stmt)
        return [(row.PFZZone, row.geometry_geojson) for row in result.all()]

    stmt = select(PFZZone)
    result = await db.execute(stmt)
    return [(row, None) for row in result.scalars().all()]


async def get_all_pfz_zones(db: AsyncSession) -> list[PFZZone]:
    stmt = select(PFZZone).order_by(PFZZone.valid_time.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())

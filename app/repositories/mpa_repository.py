import json
from typing import Any, Optional

from app.config import settings
from app.db.session import AsyncSession
from app.models.mpa_boundary import MpaBoundary
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


async def get_mpa_boundaries_within_radius(
    db: AsyncSession, lat: float, lon: float, radius_km: float
) -> list[tuple[MpaBoundary, Optional[str]]]:
    if _is_postgres():
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326).cast(Geography)
        stmt = (
            select(MpaBoundary, ST_AsGeoJSON(MpaBoundary.geometry).label("geometry_geojson"))
            .where(ST_DWithin(MpaBoundary.geometry.cast(Geography), point, radius_km * 1000))
            .order_by(MpaBoundary.effective_date.desc())
        )
        result = await db.execute(stmt)
        return [(row.MpaBoundary, row.geometry_geojson) for row in result.all()]

    stmt = select(MpaBoundary)
    result = await db.execute(stmt)
    return [(row, None) for row in result.scalars().all()]


async def get_all_mpa_boundaries(db: AsyncSession) -> list[MpaBoundary]:
    stmt = select(MpaBoundary).order_by(MpaBoundary.effective_date.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())

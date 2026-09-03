import json
import uuid
from typing import Any, Optional

from app.config import settings
from app.db.session import AsyncSession
from app.models.enums import QualityFlag
from app.models.observation import Observation
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


async def get_observations(
    db: AsyncSession,
    variable: Optional[str] = None,
    source_id: Optional[uuid.UUID] = None,
    quality_flag: Optional[QualityFlag] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
) -> list[tuple[Observation, Optional[str]]]:
    if _is_postgres():
        stmt = select(Observation, ST_AsGeoJSON(Observation.geometry).label("geometry_geojson"))
    else:
        stmt = select(Observation)

    if variable is not None:
        stmt = stmt.where(Observation.variable == variable)
    if source_id is not None:
        stmt = stmt.where(Observation.source_id == source_id)
    if quality_flag is not None:
        stmt = stmt.where(Observation.quality_flag == quality_flag)

    if _is_postgres() and lat is not None and lon is not None and radius_km is not None:
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326).cast(Geography)
        stmt = stmt.where(ST_DWithin(Observation.geometry.cast(Geography), point, radius_km * 1000))

    stmt = stmt.order_by(Observation.valid_time.desc())
    result = await db.execute(stmt)

    if _is_postgres():
        return [(row.Observation, row.geometry_geojson) for row in result.all()]

    return [(row, None) for row in result.scalars().all()]


async def get_all_observations(db: AsyncSession) -> list[Observation]:
    stmt = select(Observation).order_by(Observation.valid_time.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())

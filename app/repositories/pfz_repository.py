import json
import math
from typing import Any, Optional

from app.config import settings
from app.db.session import AsyncSession
from app.models.pfz_zone import PFZZone
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_AsGeoJSON, ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import func, select


def _serialize_geometry(geom: Any, geojson_str: Optional[str]) -> Optional[Any]:
    if geojson_str is not None:
        try:
            return json.loads(geojson_str)
        except Exception:
            return geojson_str
    if geom is None:
        return None
    return str(geom)


def _is_postgres() -> bool:
    return "postgresql" in settings.DATABASE_URL


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _extract_coords_from_components(components: dict | None) -> tuple[float, float] | None:
    if not isinstance(components, dict):
        return None
    lat = components.get("latitude")
    lon = components.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return None


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

    stmt = select(PFZZone).order_by(PFZZone.valid_time.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()

    filtered: list[tuple[PFZZone, Optional[str]]] = []
    for row in rows:
        components = row.components
        if not isinstance(components, dict):
            components = json.loads(components) if isinstance(components, str) else {}
        coords = _extract_coords_from_components(components)
        if coords is None:
            continue
        record_lat, record_lon = coords
        distance_km = _haversine_km(lat, lon, record_lat, record_lon)
        if distance_km <= radius_km:
            filtered.append((row, None))

    return filtered


async def get_all_pfz_zones(db: AsyncSession) -> list[PFZZone]:
    stmt = select(PFZZone).order_by(PFZZone.valid_time.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())

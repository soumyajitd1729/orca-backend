import json
from typing import Any, Optional

from app.config import settings
from app.db.session import AsyncSession
from app.models.mpa_boundary import MpaBoundary
from app.models.warning import Warning
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_AsGeoJSON, ST_DWithin, ST_Intersects, ST_MakePoint, ST_SetSRID
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


def _make_point(lat: float, lon: float) -> str:
    return f"POINT({lon} {lat})"


async def get_warnings_near_waypoints(
    db: AsyncSession, waypoints: list[dict], radius_km: float
) -> list[tuple[Warning, Optional[str]]]:
    if _is_postgres():
        stmt = (
            select(Warning, ST_AsGeoJSON(Warning.geometry).label("geometry_geojson"))
            .where(Warning.valid_to >= func.now())
            .order_by(Warning.valid_to.desc())
        )
        result = await db.execute(stmt)
        all_warnings = [(row.Warning, row.geometry_geojson) for row in result.all()]

        filtered = []
        for warning, geojson_str in all_warnings:
            for wp in waypoints:
                point = func.ST_SetSRID(func.ST_MakePoint(wp["lon"], wp["lat"]), 4326).cast(Geography)
                distance = func.ST_Distance(Warning.geometry.cast(Geography), point)
                dist_stmt = select(distance.label("dist")).where(Warning.id == warning.id)
                dist_result = await db.execute(dist_stmt)
                dist_m = dist_result.scalar_one_or_none()
                if dist_m is not None and dist_m <= radius_km * 1000:
                    filtered.append((warning, geojson_str))
                    break
        return filtered

    stmt = select(Warning).where(Warning.valid_to >= func.now())
    result = await db.execute(stmt)
    all_warnings = list(result.scalars().all())
    return [(row, None) for row in all_warnings]


async def get_mpa_violations_for_waypoints(
    db: AsyncSession, waypoints: list[dict]
) -> list[tuple[MpaBoundary, Optional[str]]]:
    if _is_postgres():
        violations = []
        for wp in waypoints:
            point = func.ST_SetSRID(func.ST_MakePoint(wp["lon"], wp["lat"]), 4326)
            stmt = (
                select(MpaBoundary, ST_AsGeoJSON(MpaBoundary.geometry).label("geometry_geojson"))
                .where(ST_Intersects(MpaBoundary.geometry, point))
                .order_by(MpaBoundary.effective_date.desc())
            )
            result = await db.execute(stmt)
            for row in result.all():
                violations.append((row.MpaBoundary, row.geometry_geojson))
        return violations

    stmt = select(MpaBoundary)
    result = await db.execute(stmt)
    return [(row, None) for row in result.scalars().all()]

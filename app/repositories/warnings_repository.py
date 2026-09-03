from app.config import settings
from app.db.session import AsyncSession
from app.models.enums import WarningSeverity
from app.models.warning import Warning
from geoalchemy2 import Geography
from geoalchemy2.functions import ST_AsGeoJSON, ST_DWithin, ST_MakePoint, ST_SetSRID
from sqlalchemy import func, select


def _is_postgres() -> bool:
    return "postgresql" in settings.DATABASE_URL


async def get_active_warnings_within_radius(
    db: AsyncSession, lat: float, lon: float, radius_km: float
) -> list[tuple[Warning, str | None]]:
    if _is_postgres():
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326).cast(Geography)
        stmt = (
            select(Warning, ST_AsGeoJSON(Warning.geometry).label("geometry_geojson"))
            .where(ST_DWithin(Warning.geometry.cast(Geography), point, radius_km * 1000))
            .where(Warning.valid_to >= func.now())
            .order_by(Warning.valid_to.desc())
        )
        result = await db.execute(stmt)
        return [(row.Warning, row.geometry_geojson) for row in result.all()]

    stmt = select(Warning).where(Warning.valid_to >= func.now())
    result = await db.execute(stmt)
    return [(row, None) for row in result.scalars().all()]


async def get_all_active_warnings(db: AsyncSession) -> list[Warning]:
    stmt = select(Warning).where(Warning.valid_to >= func.now()).order_by(Warning.valid_to.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_warnings_by_severity(
    db: AsyncSession, severity: WarningSeverity
) -> list[tuple[Warning, str | None]]:
    if _is_postgres():
        stmt = (
            select(Warning, ST_AsGeoJSON(Warning.geometry).label("geometry_geojson"))
            .where(Warning.severity == severity)
            .where(Warning.valid_to >= func.now())
            .order_by(Warning.valid_to.desc())
        )
        result = await db.execute(stmt)
        return [(row.Warning, row.geometry_geojson) for row in result.all()]

    stmt = select(Warning).where(Warning.severity == severity).where(Warning.valid_to >= func.now())
    result = await db.execute(stmt)
    return [(row, None) for row in result.scalars().all()]

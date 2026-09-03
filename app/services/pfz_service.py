from app.models.pfz_zone import PFZZone
from app.repositories import pfz_repository
from app.schemas.pfz import PFZZoneOut


def _to_pfz_zone_out(row: PFZZone, geojson_str: str | None) -> PFZZoneOut:
    return PFZZoneOut(
        id=str(row.id),
        geometry=pfz_repository._serialize_geometry(row.geometry, geojson_str),
        score=row.score,
        components=row.components or {},
        valid_time=row.valid_time,
    )


async def get_pfz_zones(lat: float, lon: float, radius_km: float, db) -> list[PFZZoneOut]:
    rows = await pfz_repository.get_pfz_zones_within_radius(db, lat, lon, radius_km)
    return [_to_pfz_zone_out(row, geojson_str) for row, geojson_str in rows]


async def get_all_pfz_zones(db) -> list[PFZZoneOut]:
    rows = await pfz_repository.get_all_pfz_zones(db)
    return [_to_pfz_zone_out(row, None) for row in rows]

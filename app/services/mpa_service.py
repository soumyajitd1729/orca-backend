from app.models.mpa_boundary import MpaBoundary
from app.repositories import mpa_repository
from app.schemas.mpa import MpaBoundaryOut


def _to_mpa_boundary_out(row: MpaBoundary, geojson_str: str | None) -> MpaBoundaryOut:
    return MpaBoundaryOut(
        id=str(row.id),
        name=row.name,
        geometry=mpa_repository._serialize_geometry(row.geometry, geojson_str),
        source=row.source,
        version=row.version,
        effective_date=row.effective_date,
    )


async def get_mpa_boundaries(lat: float, lon: float, radius_km: float, db) -> list[MpaBoundaryOut]:
    rows = await mpa_repository.get_mpa_boundaries_within_radius(db, lat, lon, radius_km)
    return [_to_mpa_boundary_out(row, geojson_str) for row, geojson_str in rows]


async def get_all_mpa_boundaries(db) -> list[MpaBoundaryOut]:
    rows = await mpa_repository.get_all_mpa_boundaries(db)
    return [_to_mpa_boundary_out(row, None) for row in rows]

from app.models.enums import QualityFlag
from app.repositories import observations_repository, pfz_repository, warnings_repository
from app.schemas.point import PointResponse


async def get_point_data(db, lat: float, lon: float, radius_km: float) -> PointResponse:
    obs_rows = await observations_repository.get_observations(
        db, lat=lat, lon=lon, radius_km=radius_km
    )
    observations = [
        {
            "id": str(row.id),
            "variable": row.variable,
            "value": row.value,
            "unit": row.unit,
            "geometry": observations_repository._serialize_geometry(row.geometry, geojson_str),
            "observed_at": row.valid_time.isoformat(),
            "source_time": row.source_time.isoformat(),
            "source_id": str(row.source_id) if row.source_id else None,
            "quality_flag": row.quality_flag.value,
            "confidence": row.confidence,
        }
        for row, geojson_str in obs_rows
    ]

    warn_rows = await warnings_repository.get_active_warnings_within_radius(
        db, lat, lon, radius_km
    )
    warnings = [
        {
            "id": str(row.id),
            "type": row.type,
            "severity": row.severity.value,
            "description": f"{row.type} advisory issued by {row.issued_by}",
            "issued_by": row.issued_by,
            "valid_from": row.valid_from.isoformat(),
            "valid_to": row.valid_to.isoformat(),
            "geometry": warnings_repository._serialize_geometry(row.geometry, geojson_str),
        }
        for row, geojson_str in warn_rows
    ]

    pfz_rows = await pfz_repository.get_pfz_zones_within_radius(db, lat, lon, radius_km)
    pfz_zones = [
        {
            "id": str(row.id),
            "score": row.score,
            "components": row.components or {},
            "valid_time": row.valid_time.isoformat(),
            "geometry": pfz_repository._serialize_geometry(row.geometry, geojson_str),
        }
        for row, geojson_str in pfz_rows
    ]

    return PointResponse(
        observations=observations,
        warnings=warnings,
        pfz_zones=pfz_zones,
    )

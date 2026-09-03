import uuid
from typing import Optional

from app.models.observation import Observation
from app.models.enums import QualityFlag
from app.repositories import observations_repository
from app.schemas.observations import ObservationOut


def _to_observation_out(row: Observation, geojson_str: str | None) -> ObservationOut:
    return ObservationOut(
        id=str(row.id),
        variable=row.variable,
        value=row.value,
        unit=row.unit,
        geometry=observations_repository._serialize_geometry(row.geometry, geojson_str),
        observed_at=row.valid_time,
        source_time=row.source_time,
        source_id=str(row.source_id) if row.source_id else None,
        quality_flag=row.quality_flag,
        confidence=row.confidence,
    )


async def get_observations(
    db,
    variable: Optional[str] = None,
    source_id: Optional[str] = None,
    quality_flag: Optional[QualityFlag] = None,
    lat: Optional[float] = None,
    lon: Optional[float] = None,
    radius_km: Optional[float] = None,
) -> list[ObservationOut]:
    parsed_source_id: Optional[uuid.UUID] = None
    if source_id is not None:
        try:
            parsed_source_id = uuid.UUID(source_id)
        except ValueError:
            parsed_source_id = None

    rows = await observations_repository.get_observations(
        db,
        variable=variable,
        source_id=parsed_source_id,
        quality_flag=quality_flag,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
    )
    return [_to_observation_out(row, geojson_str) for row, geojson_str in rows]


async def get_all_observations(db) -> list[ObservationOut]:
    rows = await observations_repository.get_all_observations(db)
    return [_to_observation_out(row, None) for row in rows]

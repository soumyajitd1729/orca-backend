from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.envelope import build_envelope
from app.models.enums import QualityFlag
from app.schemas.observations import ObservationQuery
from app.services import observations_service

router = APIRouter()


@router.get("/observations")
async def list_observations(
    variable: str | None = Query(None, description="Filter by observation variable"),
    source_id: str | None = Query(None, description="Filter by data source UUID"),
    quality_flag: QualityFlag | None = Query(None, description="Filter by quality flag"),
    lat: float | None = Query(None, ge=-90.0, le=90.0, description="Latitude of the query point"),
    lon: float | None = Query(None, ge=-180.0, le=180.0, description="Longitude of the query point"),
    radius_km: float = Query(10.0, gt=0, description="Search radius in kilometers"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    observations = await observations_service.get_observations(
        db,
        variable=variable,
        source_id=source_id,
        quality_flag=quality_flag,
        lat=lat,
        lon=lon,
        radius_km=radius_km,
    )
    return build_envelope(data=[o.model_dump() for o in observations])

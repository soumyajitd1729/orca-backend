from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.envelope import build_envelope
from app.schemas.mpa import MpaQuery
from app.services import mpa_service

router = APIRouter()


@router.get("/mpa-boundaries")
async def list_mpa_boundaries(
    lat: float | None = Query(None, ge=-90.0, le=90.0, description="Latitude of the query point"),
    lon: float | None = Query(None, ge=-180.0, le=180.0, description="Longitude of the query point"),
    radius_km: float = Query(10.0, gt=0, description="Search radius in kilometers"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if lat is not None and lon is not None:
        boundaries = await mpa_service.get_mpa_boundaries(lat, lon, radius_km, db)
    else:
        boundaries = await mpa_service.get_all_mpa_boundaries(db)
    return build_envelope(data=[b.model_dump() for b in boundaries])

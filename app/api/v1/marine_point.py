from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.envelope import build_envelope
from app.schemas.point import PointQuery
from app.services import point_service

router = APIRouter()


@router.get("/marine/point")
async def get_marine_point(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude of the query point"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude of the query point"),
    radius_km: float = Query(10.0, gt=0, description="Search radius in kilometers"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await point_service.get_point_data(db, lat, lon, radius_km)
    return build_envelope(data=result.model_dump())

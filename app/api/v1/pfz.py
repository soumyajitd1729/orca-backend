from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.envelope import build_envelope
from app.models.enums import WarningSeverity
from app.schemas.pfz import PFZQuery
from app.services import pfz_service

router = APIRouter()


@router.get("/pfz-zones")
@router.get("/pfz/nearby")
async def list_pfz_zones(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude of the query point"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude of the query point"),
    radius_km: float = Query(10.0, gt=0, description="Search radius in kilometers"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    pfz_zones = await pfz_service.get_pfz_zones(lat, lon, radius_km, db)
    return build_envelope(data=[z.model_dump() for z in pfz_zones])

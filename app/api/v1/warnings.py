from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.envelope import build_envelope
from app.models.enums import WarningSeverity
from app.schemas.warnings import WarningOut
from app.services import warnings_service

router = APIRouter()


@router.get("/warnings")
async def list_warnings(
    lat: float = Query(..., ge=-90.0, le=90.0, description="Latitude of the query point"),
    lon: float = Query(..., ge=-180.0, le=180.0, description="Longitude of the query point"),
    radius_km: float = Query(10.0, gt=0, description="Search radius in kilometers"),
    severity: WarningSeverity | None = Query(None, description="Filter by warning severity"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if severity is not None:
        warnings = await warnings_service.get_warnings_by_severity(db, severity)
    else:
        warnings = await warnings_service.get_warnings(lat, lon, radius_km, db)
    return build_envelope(data=[w.model_dump() for w in warnings])

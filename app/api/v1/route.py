from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.envelope import build_envelope
from app.schemas.route import RouteEvaluationRequest, RouteEvaluationOut
from app.services import route_service

router = APIRouter()


@router.post("/route/evaluate")
async def evaluate_route(
    payload: RouteEvaluationRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    waypoints = [wp.model_dump() for wp in payload.waypoints]
    result = await route_service.evaluate_route(
        db, waypoints, payload.vessel_type, payload.max_wave_height
    )
    return build_envelope(data=result.model_dump())

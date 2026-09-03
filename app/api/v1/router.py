from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.warnings import router as warnings_router
from app.api.v1.pfz import router as pfz_router
from app.api.v1.mpa import router as mpa_router
from app.api.v1.observations import router as observations_router
from app.api.v1.route import router as route_router
from app.api.v1.layers import router as layers_router
from app.api.v1.marine_point import router as marine_point_router
from app.envelope import build_envelope

router = APIRouter()
router.include_router(health_router)
router.include_router(warnings_router)
router.include_router(pfz_router)
router.include_router(mpa_router)
router.include_router(observations_router)
router.include_router(route_router)
router.include_router(layers_router)
router.include_router(marine_point_router)


@router.get("/ping")
async def ping():
    return build_envelope(data={"status": "ok"})

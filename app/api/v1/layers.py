from fastapi import APIRouter

from app.envelope import build_envelope
from app.services import layers_service

router = APIRouter()


@router.get("/layers")
async def list_layers():
    layers = layers_service.get_available_layers()
    return build_envelope(data=[layer.model_dump() for layer in layers])

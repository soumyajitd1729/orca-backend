from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.envelope import build_envelope
from app.schemas.health import SourceDetail
from app.services import health_service

router = APIRouter()


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    summary = await health_service.get_health_summary(db)
    return build_envelope(data=summary.model_dump())


@router.get("/health/sources")
async def list_sources(db: AsyncSession = Depends(get_db)):
    sources = await health_service.get_all_source_details(db)
    return build_envelope(data=[s.model_dump() for s in sources])


@router.get("/health/sources/{source_name}")
async def get_source(source_name: str, db: AsyncSession = Depends(get_db)):
    source = await health_service.get_source_detail(db, source_name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Data source '{source_name}' not found")
    return build_envelope(data=source.model_dump())

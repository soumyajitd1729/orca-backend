import logging
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
from sqlalchemy import select
from app.config import settings
from app.api.v1.router import router as api_v1_router
from app.envelope import build_envelope
from app.exceptions import register_exception_handlers, OrcaException

logger = logging.getLogger("orca")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Enable schema creation and auto-patching for both local and production environments
    from app.db.base import Base
    from app.db.session import AsyncSessionLocal, engine
    from app.models.data_source_health import DataSourceHealth
    from app.models.enums import SourceStatus
    from sqlalchemy import text

    async with engine.begin() as conn:
        # Create tables if they don't exist yet
        await conn.run_sync(Base.metadata.create_all)
        
        # Safely auto-patch missing columns in production without Alembic
        try:
            await conn.execute(
                text("ALTER TABLE pfz_zones ADD COLUMN IF NOT EXISTS source_type VARCHAR;")
            )
        except Exception as e:
            logger.warning(f"Note on auto-patching columns: {e}")

    # Seed data source health if empty
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(DataSourceHealth))).scalars().first()
        if existing is None:
            for name, priority in (("incois", 1), ("mosdac", 2), ("imd", 3)):
                session.add(
                    DataSourceHealth(
                        name=name, priority=priority, status=SourceStatus.unavailable
                    )
                )
            await session.commit()
    yield

app = FastAPI(
    title="ORCA Backend",
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def error_envelope_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception:
        logger.exception("Unhandled exception during request")
        return JSONResponse(
            status_code=500,
            content=build_envelope(errors=["Internal server error"]),
        )


@app.get("/ping")
async def ping(request: Request):
    return build_envelope(data={"status": "ok"})


cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


register_exception_handlers(app)

app.include_router(api_v1_router, prefix="/api/v1")

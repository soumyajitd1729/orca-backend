from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.enums import SourceStatus

SourceStatusLiteral = Literal["live", "cached", "stale", "unavailable"]


class SourceHealth(BaseModel):
    status: SourceStatusLiteral
    last_success_at: Optional[str] = None


class HealthData(BaseModel):
    incois: SourceHealth
    mosdac: SourceHealth
    imd: SourceHealth


class SourceDetail(BaseModel):
    name: str
    priority: int
    status: SourceStatusLiteral
    last_fetch_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SourceUpdate(BaseModel):
    status: SourceStatusLiteral = Field(..., description="New status for the data source")
    last_fetch_at: Optional[str] = Field(None, description="ISO8601 timestamp of last successful fetch")


class HealthResponse(BaseModel):
    data: HealthData
    errors: list[str] = []
    meta: dict = {}

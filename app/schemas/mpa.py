from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class MpaQuery(BaseModel):
    lat: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Latitude of the query point")
    lon: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Longitude of the query point")
    radius_km: float = Field(default=10.0, gt=0, description="Search radius in kilometers")


class MpaBoundaryOut(BaseModel):
    id: str
    name: str
    geometry: Optional[Any] = None
    source: str
    version: str
    effective_date: datetime

from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class PFZQuery(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude of the query point")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude of the query point")
    radius_km: float = Field(default=10.0, gt=0, description="Search radius in kilometers")


class PFZZoneOut(BaseModel):
    id: str
    geometry: Optional[Any] = None
    score: Optional[float] = None
    components: dict
    valid_time: datetime
    source_type: Optional[str] = None
    source_name: Optional[str] = None
    sector: Optional[str] = None
    landing_center: Optional[str] = None
    depth: Optional[str] = None
    distance_km: Optional[float] = None
    direction: Optional[str] = None
    forecast_date: Optional[date] = None
    valid_until: Optional[date] = None

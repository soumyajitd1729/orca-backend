from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.enums import QualityFlag


class ObservationQuery(BaseModel):
    variable: Optional[str] = Field(None, description="Filter by observation variable (e.g. sst, chlorophyll)")
    source_id: Optional[str] = Field(None, description="Filter by data source UUID")
    quality_flag: Optional[QualityFlag] = Field(None, description="Filter by quality flag")
    lat: Optional[float] = Field(None, ge=-90.0, le=90.0, description="Latitude of the query point")
    lon: Optional[float] = Field(None, ge=-180.0, le=180.0, description="Longitude of the query point")
    radius_km: float = Field(default=10.0, gt=0, description="Search radius in kilometers")


class ObservationOut(BaseModel):
    id: str
    variable: str
    value: float
    unit: str
    geometry: Optional[Any] = None
    observed_at: datetime
    source_time: datetime
    source_id: Optional[str] = None
    quality_flag: QualityFlag
    confidence: float

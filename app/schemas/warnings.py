from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.enums import WarningSeverity


class WarningQuery(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude of the query point")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude of the query point")
    radius_km: float = Field(default=10.0, gt=0, description="Search radius in kilometers")
    severity: Optional[WarningSeverity] = Field(default=None, description="Filter by warning severity")


class WarningOut(BaseModel):
    id: str
    type: str
    title: str
    description: str
    severity: WarningSeverity
    geometry: Optional[Any] = None
    issued_by: str
    valid_from: datetime
    valid_to: datetime

from typing import Any, Optional

from pydantic import BaseModel, Field


class PointQuery(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude of the query point")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude of the query point")
    radius_km: float = Field(default=10.0, gt=0, description="Search radius in kilometers")


class PointResponse(BaseModel):
    observations: list[dict] = []
    warnings: list[dict] = []
    pfz_zones: list[dict] = []

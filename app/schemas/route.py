from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class Waypoint(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class RouteEvaluationRequest(BaseModel):
    waypoints: list[Waypoint] = Field(..., min_length=2, description="Ordered list of [lat, lon] waypoints")
    vessel_type: Optional[str] = Field(None, description="Optional vessel type identifier")
    max_wave_height: Optional[float] = Field(None, gt=0, description="Optional maximum tolerable wave height in meters")

    @field_validator("waypoints")
    @classmethod
    def validate_waypoints(cls, value: list[Waypoint]) -> list[Waypoint]:
        if len(value) < 2:
            raise ValueError("At least two waypoints are required to evaluate a route")
        return value


class HazardWarningOut(BaseModel):
    id: str
    type: str
    severity: str
    description: str
    issued_by: str
    valid_from: str
    valid_to: str
    geometry: Optional[Any] = None


class GeofenceViolationOut(BaseModel):
    id: str
    name: str
    source: str
    version: str
    effective_date: str
    geometry: Optional[Any] = None


class RouteEvaluationOut(BaseModel):
    route_cost: float
    risk_level: str
    geofence_violations: list[GeofenceViolationOut] = []
    hazard_warnings: list[HazardWarningOut] = []

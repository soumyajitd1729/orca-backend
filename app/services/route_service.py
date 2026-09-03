import math
from typing import Any, Optional

from app.models.enums import WarningSeverity
from app.models.mpa_boundary import MpaBoundary
from app.models.warning import Warning
from app.repositories import route_repository
from app.schemas.route import GeofenceViolationOut, HazardWarningOut, RouteEvaluationOut
from app.schemas.warnings import WarningOut
from app.services import mpa_service, warnings_service

EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_KM * c


def _compute_route_cost_km(waypoints: list[dict]) -> float:
    total = 0.0
    for i in range(len(waypoints) - 1):
        total += _haversine_km(
            waypoints[i]["lat"],
            waypoints[i]["lon"],
            waypoints[i + 1]["lat"],
            waypoints[i + 1]["lon"],
        )
    return round(total, 3)


def _compute_risk_level(violation_count: int, warnings: list[dict]) -> str:
    high_severity = any(w.get("severity") in ("high", "extreme") for w in warnings)
    moderate_severity = any(w.get("severity") == "moderate" for w in warnings)

    if violation_count > 0 or high_severity:
        return "high"
    if moderate_severity:
        return "medium"
    return "low"


async def evaluate_route(db, waypoints: list[dict], vessel_type: Optional[str], max_wave_height: Optional[float]) -> RouteEvaluationOut:
    route_cost = _compute_route_cost_km(waypoints)

    radius_km = 10.0
    if max_wave_height is not None:
        radius_km = max(radius_km, float(max_wave_height) * 5.0)

    warning_rows = await route_repository.get_warnings_near_waypoints(db, waypoints, radius_km)
    hazard_warnings = [
        HazardWarningOut(
            id=str(row.id),
            type=row.type,
            severity=row.severity.value,
            description=f"{row.type} advisory issued by {row.issued_by}",
            issued_by=row.issued_by,
            valid_from=row.valid_from.isoformat(),
            valid_to=row.valid_to.isoformat(),
            geometry=route_repository._serialize_geometry(row.geometry, geojson_str),
        )
        for row, geojson_str in warning_rows
    ]

    violation_rows = await route_repository.get_mpa_violations_for_waypoints(db, waypoints)
    geofence_violations = [
        GeofenceViolationOut(
            id=str(row.id),
            name=row.name,
            source=row.source,
            version=row.version,
            effective_date=row.effective_date.isoformat(),
            geometry=route_repository._serialize_geometry(row.geometry, geojson_str),
        )
        for row, geojson_str in violation_rows
    ]

    risk_level = _compute_risk_level(len(geofence_violations), [w.model_dump() for w in hazard_warnings])

    return RouteEvaluationOut(
        route_cost=route_cost,
        risk_level=risk_level,
        geofence_violations=geofence_violations,
        hazard_warnings=hazard_warnings,
    )

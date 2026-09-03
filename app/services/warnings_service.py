import json
from typing import Any, Optional

from app.models.enums import WarningSeverity
from app.models.warning import Warning
from app.repositories import warnings_repository
from app.schemas.warnings import WarningOut


def _serialize_geometry(geom: Any, geojson_str: Optional[str]) -> Optional[Any]:
    if geojson_str is not None:
        try:
            return json.loads(geojson_str)
        except Exception:
            return geojson_str
    if geom is None:
        return None
    return str(geom)


def _to_warning_out(row: Warning, geojson_str: Optional[str]) -> WarningOut:
    return WarningOut(
        id=str(row.id),
        type=row.type,
        title=row.type,
        description=f"{row.type} advisory issued by {row.issued_by}",
        severity=row.severity,
        geometry=_serialize_geometry(row.geometry, geojson_str),
        issued_by=row.issued_by,
        valid_from=row.valid_from,
        valid_to=row.valid_to,
    )


async def get_warnings(lat: float, lon: float, radius_km: float, db) -> list[WarningOut]:
    rows = await warnings_repository.get_active_warnings_within_radius(
        db, lat, lon, radius_km
    )
    return [_to_warning_out(row, geojson_str) for row, geojson_str in rows]


async def get_all_warnings(db) -> list[WarningOut]:
    rows = await warnings_repository.get_all_active_warnings(db)
    return [_to_warning_out(row, None) for row in rows]


async def get_warnings_by_severity(db, severity: WarningSeverity) -> list[WarningOut]:
    rows = await warnings_repository.get_warnings_by_severity(db, severity)
    return [_to_warning_out(row, geojson_str) for row, geojson_str in rows]

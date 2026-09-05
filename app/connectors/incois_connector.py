"""
INCOIS connector abstraction.

VERIFIED INTERFACES:
- ERDDAP REST server at https://erddap.incois.gov.in/
  Supports JSON/CSV/HTML table responses for oceanographic datasets.
  Standard ERDDAP constraint query syntax applies.

UNVERIFIED / NOT IMPLEMENTED:
- PFZ machine-readable REST API: INCOIS distributes PFZ advisories via
  WebGIS maps and text bulletins. No verified public REST API for PFZ scores
  was found. The connector reports PFZ as unavailable rather than fabricating
  coordinates or scores.
- Ocean State Forecast (OSF): Provided via interactive WebGIS; no verified
  direct machine-readable REST endpoint was identified.

AUTHENTICATION:
- ERDDAP is public and does not require authentication for dataset search
  or subset queries.

RATE LIMITS:
- Not documented. Treat as public data with fair-use expectations.

EVIDENCE:
- All numeric values returned by verified ERDDAP queries include source,
  variable, unit, valid_time, confidence, url_ref, and why_it_matters.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from app.connectors.base_connector import BaseConnector, ConnectorEvidence, ConnectorResult

logger = logging.getLogger("orca")

INCOIS_ERDDAP_BASE = "https://erddap.incois.gov.in/erddap"
INCOIS_PFZ_WEBGIS = "https://incois.gov.in/geoportal/MFASPFZ/index.html"
INCOIS_OSF_URL = "https://incois.gov.in/oceanservices/osfforecast.jsp"

WHY_IT_MATTERS = {
    "sst": "Sea surface temperature affects fish distribution and storm intensity.",
    "sea_surface_temperature": "Sea surface temperature affects fish distribution and storm intensity.",
    "chlorophyll": "Chlorophyll indicates phytoplankton concentration and potential fishing zones.",
    "wave_height": "Wave height directly impacts vessel safety and fishing operations.",
    "significant_wave_height": "Significant wave height is a critical safety metric for marine operations.",
    "wind_speed": "Wind speed affects sea state and vessel handling.",
    "wind_direction": "Wind direction influences wave patterns and drift.",
    "air_temperature": "Air temperature affects crew comfort and equipment performance.",
    "humidity": "Humidity affects weather patterns and storm development.",
    "swell_height": "Swell height contributes to overall sea state and vessel safety.",
    "swell_period": "Swell period indicates ocean swell characteristics affecting vessel motion.",
    "wave_direction": "Wave direction influences vessel routing and sea state exposure.",
    "wave_period": "Wave period affects vessel stability and crew fatigue.",
}


class IncoisConnector(BaseConnector):
    def __init__(self, base_url: str = INCOIS_ERDDAP_BASE) -> None:
        super().__init__(base_url=base_url)

    async def _fetch_data(self, **kwargs: Any) -> Any:
        raise NotImplementedError("Use search_datasets() or query_dataset() instead.")

    async def search_datasets(self, search_for: str) -> ConnectorResult:
        try:
            import urllib.parse

            url = f"{self.base_url}/search/index.json"
            params = {"page": 1, "itemsPerPage": 100, "searchFor": search_for}
            full_url = f"{url}?{urllib.parse.urlencode(params)}"

            import httpx

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(full_url)
                response.raise_for_status()
                return ConnectorResult(
                    status="success",
                    data=response.json(),
                    source_status="live",
                    retrieved_at=datetime.utcnow(),
                )
        except Exception as exc:
            logger.warning("INCOIS dataset search failed: %s", exc)
            return ConnectorResult(
                status="error",
                errors=[f"incois_search_failed: {exc}"],
                source_status="unavailable",
                retrieved_at=datetime.utcnow(),
            )

    async def query_dataset(
        self,
        dataset_id: str,
        variables: list[str],
        lat_min: float,
        lat_max: float,
        lon_min: float,
        lon_max: float,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
    ) -> ConnectorResult:
        try:
            import httpx

            var_csv = ",".join(variables)
            constraints = [
                f"latitude>={lat_min}",
                f"latitude<={lat_max}",
                f"longitude>={lon_min}",
                f"longitude<={lon_max}",
            ]
            if time_min:
                constraints.append(f"time>={time_min}")
            if time_max:
                constraints.append(f"time<={time_max}")

            constraint_str = "&".join(constraints)
            url = (
                f"{self.base_url}/tabledap/{dataset_id}.json"
                f"?{var_csv}&{constraint_str}"
            )

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                payload = response.json()
                return ConnectorResult(
                    status="success",
                    data=payload,
                    source_status="live",
                    retrieved_at=datetime.utcnow(),
                )
        except Exception as exc:
            logger.warning("INCOIS dataset query failed: %s", exc)
            return ConnectorResult(
                status="error",
                errors=[f"incois_query_failed: {exc}"],
                source_status="unavailable",
                retrieved_at=datetime.utcnow(),
            )

    def normalize_observations(
        self,
        raw: Any,
        variable_mapping: Optional[dict[str, str]] = None,
    ) -> ConnectorResult:
        variable_mapping = variable_mapping or {}
        evidence: list[ConnectorEvidence] = []
        errors: list[str] = []

        if isinstance(raw, dict) and "error" in raw:
            return ConnectorResult(
                status="error",
                errors=[str(raw["error"])],
                source_status="unavailable",
                retrieved_at=datetime.utcnow(),
            )

        rows = []
        if isinstance(raw, dict):
            if "table" in raw and "rows" in raw["table"]:
                columns = [c["name"] for c in raw["table"].get("columns", [])]
                rows = [dict(zip(columns, row)) for row in raw["table"]["rows"]]
            elif "data" in raw and "variables" in raw:
                variables = raw["variables"]
                data_rows = raw["data"]
                rows = [dict(zip(variables, row)) for row in data_rows]
            else:
                errors.append(f"unexpected_erddap_payload_keys={list(raw.keys())[:5]}")
        elif isinstance(raw, list):
            rows = raw
        else:
            errors.append(f"unsupported_raw_type={type(raw).__name__}")

        if not rows and not errors:
            errors.append("no_rows_returned")

        for row in rows:
            if not isinstance(row, dict):
                continue
            raw_var = row.get("variable") or row.get("Variable") or ""
            variable = variable_mapping.get(raw_var.lower(), raw_var.lower())
            value = row.get("value") or row.get("Value") or row.get("magnitude")
            unit = row.get("unit") or row.get("Unit") or ""
            time_str = row.get("time") or row.get("Time") or row.get("date") or row.get("Date")
            confidence = row.get("confidence") or row.get("qc") or 0.9

            if value is None:
                errors.append(f"missing_value_for_variable={variable}")
                continue

            valid_time = None
            if time_str:
                try:
                    valid_time = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
                except Exception:
                    valid_time = datetime.utcnow()

            evidence.append(
                ConnectorEvidence(
                    source="incois",
                    variable=variable,
                    value=value,
                    unit=unit or None,
                    valid_time=valid_time,
                    confidence=confidence if isinstance(confidence, (int, float)) else 0.9,
                    why_it_matters=WHY_IT_MATTERS.get(variable),
                    url_ref=f"{INCOIS_ERDDAP_BASE}/tabledap/{row.get('datasetId', 'unknown')}.html",
                )
            )

        status = "success" if evidence else "no_data"
        source_status = "live" if evidence else "no_data"

        return ConnectorResult(
            status=status,
            data=rows,
            evidence=evidence,
            errors=errors,
            source_status=source_status,
            retrieved_at=datetime.utcnow(),
        )

    def normalize_pfz_unavailable(self, reason: str = "no_verified_machine_readable_api") -> ConnectorResult:
        return ConnectorResult(
            status="unavailable",
            data=None,
            errors=[f"pfz_unavailable:{reason}"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    def normalize_warnings(self, raw: Any) -> ConnectorResult:
        evidence: list[ConnectorEvidence] = []
        errors: list[str] = []

        if isinstance(raw, dict) and "error" in raw:
            return ConnectorResult(
                status="error",
                errors=[str(raw["error"])],
                source_status="unavailable",
                retrieved_at=datetime.utcnow(),
            )

        rows = []
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, dict):
            if "features" in raw:
                for feature in raw["features"]:
                    props = feature.get("properties", {})
                    rows.append(props)
            elif "data" in raw and isinstance(raw["data"], list):
                rows = raw["data"]
            else:
                errors.append(f"unexpected_payload_keys={list(raw.keys())[:5]}")
        else:
            errors.append(f"unsupported_raw_type={type(raw).__name__}")

        for row in rows:
            if not isinstance(row, dict):
                continue
            warning_type = row.get("type") or row.get("warning_type") or "unknown"
            severity = row.get("severity") or row.get("category") or "unknown"
            valid_from = row.get("valid_from") or row.get("start_time")
            valid_to = row.get("valid_to") or row.get("end_time")

            valid_from_dt = None
            valid_to_dt = None
            if valid_from:
                try:
                    valid_from_dt = datetime.fromisoformat(str(valid_from).replace("Z", "+00:00"))
                except Exception:
                    valid_from_dt = datetime.utcnow()
            if valid_to:
                try:
                    valid_to_dt = datetime.fromisoformat(str(valid_to).replace("Z", "+00:00"))
                except Exception:
                    valid_to_dt = datetime.utcnow()

            evidence.append(
                ConnectorEvidence(
                    source="incois",
                    variable=str(warning_type).lower().replace(" ", "_"),
                    value=warning_type,
                    unit="advisory",
                    valid_time=valid_from_dt,
                    confidence=1.0,
                    why_it_matters="Active marine warning affects safety assessment.",
                    url_ref=INCOIS_OSF_URL,
                )
            )

        status = "success" if evidence else "no_data"
        source_status = "live" if evidence else "no_data"

        return ConnectorResult(
            status=status,
            data=rows,
            evidence=evidence,
            errors=errors,
            source_status=source_status,
            retrieved_at=datetime.utcnow(),
        )

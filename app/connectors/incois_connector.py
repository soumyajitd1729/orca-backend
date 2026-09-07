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

SSL/TLS NOTE:
- The INCOIS ERDDAP server does not send the GlobalSign RSA OV SSL CA 2018
  intermediate certificate. This environment includes the intermediate in
  `orca_ca_bundle.pem` and the connector uses it if present.

EVIDENCE:
- All numeric values returned by verified ERDDAP queries include source,
  variable, unit, valid_time, confidence, url_ref, and why_it_matters.
"""

from __future__ import annotations

import json
import logging
import os
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.connectors.base_connector import BaseConnector, ConnectorEvidence, ConnectorResult

logger = logging.getLogger("orca")

INCOIS_ERDDAP_BASE = "https://erddap.incois.gov.in/erddap"
INCOIS_PFZ_WEBGIS = "https://incois.gov.in/geoportal/MFASPFZ/index.html"
INCOIS_OSF_URL = "https://incois.gov.in/oceanservices/osfforecast.jsp"
INCOIS_CA_BUNDLE = Path(__file__).resolve().parent.parent.parent / "orca_ca_bundle.pem"

WHY_IT_MATTERS = {
    "sst": "Sea surface temperature affects fish distribution and storm intensity.",
    "sea_surface_temperature": "Sea surface temperature affects fish distribution and storm intensity.",
    "temperature": "Water temperature affects marine ecosystem behavior and vessel cooling systems.",
    "chlorophyll": "Chlorophyll indicates phytoplankton concentration and potential fishing zones.",
    "wave_height": "Wave height directly impacts vessel safety and fishing operations.",
    "significant_wave_height": "Significant wave height is a critical safety metric for marine operations.",
    "wind_speed": "Wind speed affects sea state and vessel handling.",
    "wind_direction": "Wind direction influences wave patterns and drift.",
    "air_temperature": "Air temperature affects crew comfort and equipment performance.",
    "humidity": "Humidity affects weather patterns and storm development.",
    "salinity": "Salinity affects water density and marine ecosystem behavior.",
    "psal": "Salinity affects water density and marine ecosystem behavior.",
    "swell_height": "Swell height contributes to overall sea state and vessel safety.",
    "swell_period": "Swell period indicates ocean swell characteristics affecting vessel motion.",
    "wave_direction": "Wave direction influences vessel routing and sea state exposure.",
    "wave_period": "Wave period affects vessel stability and crew fatigue.",
}


class IncoisConnector(BaseConnector):
    def __init__(self, base_url: str = INCOIS_ERDDAP_BASE) -> None:
        super().__init__(base_url=base_url)
        self._ca_bundle: str | ssl.SSLContext = True
        if INCOIS_CA_BUNDLE.exists():
            self._ca_bundle = ssl.create_default_context(cafile=str(INCOIS_CA_BUNDLE))

    async def _fetch_data(self, **kwargs: Any) -> Any:
        raise NotImplementedError("Use search_datasets() or query_dataset() instead.")

    async def search_datasets(self, search_for: str) -> ConnectorResult:
        try:
            import urllib.parse

            url = f"{self.base_url}/search/index.json"
            params = {"page": 1, "itemsPerPage": 100, "searchFor": search_for}
            full_url = f"{url}?{urllib.parse.urlencode(params)}"

            import httpx

            async with httpx.AsyncClient(timeout=self.timeout, verify=self._ca_bundle) as client:
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

            dataset_id = self._normalize_dataset_id(dataset_id)
            if "://" in dataset_id:
                logger.warning("dataset_id still contains URL scheme after normalization: %s", dataset_id)
                dataset_id = dataset_id.rstrip("/").split("/")[-1].replace(".html", "").replace(".json", "")
            normalized_vars = [v for v in variables if v and v.strip()]
            for coord in {"latitude", "longitude", "time"}:
                if coord not in [v.lower() for v in normalized_vars]:
                    normalized_vars.append(coord)
            var_csv = ",".join(normalized_vars)
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

            async with httpx.AsyncClient(timeout=self.timeout, verify=self._ca_bundle) as client:
                response = await client.get(url)
                if response.status_code == 404 and "no matching results" in response.text:
                    return ConnectorResult(
                        status="no_data",
                        data=None,
                        errors=["incois_query_no_matching_results"],
                        source_status="no_data",
                        retrieved_at=datetime.utcnow(),
                    )
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

    async def query_griddap(
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

            dataset_id = self._normalize_dataset_id(dataset_id)
            if "://" in dataset_id:
                logger.warning("dataset_id still contains URL scheme after normalization: %s", dataset_id)
                dataset_id = dataset_id.rstrip("/").split("/")[-1].replace(".html", "").replace(".json", "")
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
                f"{self.base_url}/griddap/{dataset_id}.json"
                f"?{var_csv}&{constraint_str}"
            )

            async with httpx.AsyncClient(timeout=self.timeout, verify=self._ca_bundle) as client:
                response = await client.get(url)
                if response.status_code == 404 and "no matching results" in response.text:
                    return ConnectorResult(
                        status="no_data",
                        data=None,
                        errors=["incois_griddap_no_matching_results"],
                        source_status="no_data",
                        retrieved_at=datetime.utcnow(),
                    )
                response.raise_for_status()
                payload = response.json()
                return ConnectorResult(
                    status="success",
                    data=payload,
                    source_status="live",
                    retrieved_at=datetime.utcnow(),
                )
        except Exception as exc:
            logger.warning("INCOIS griddap query failed: %s", exc)
            return ConnectorResult(
                status="error",
                errors=[f"incois_griddap_failed: {exc}"],
                source_status="unavailable",
                retrieved_at=datetime.utcnow(),
            )

    def select_observation_dataset(self, search_result: ConnectorResult) -> dict | None:
        if search_result.status != "success" or not search_result.data:
            return None

        data = search_result.data

        if isinstance(data, list):
            candidates = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                dataset_id = str(item.get("datasetID") or item.get("dataset_id") or "").strip()
                dataset_id = self._normalize_dataset_id(dataset_id)
                if not dataset_id or dataset_id.lower() in {"alldatasets", "alldatasets"}:
                    continue
                url = str(item.get("url") or item.get("publicUrl") or item.get("accessUrl") or "")
                if "/tabledap/" in url:
                    candidates.append((dataset_id, url, "tabledap"))
                elif "/griddap/" in url:
                    candidates.append((dataset_id, url, "griddap"))
            if not candidates:
                return None
            tabledap_candidates = [c for c in candidates if c[2] == "tabledap"]
            if tabledap_candidates:
                dataset_id, url, access_method = tabledap_candidates[0]
            else:
                dataset_id, url, access_method = candidates[0]
            return {
                "dataset_id": dataset_id,
                "url": url,
                "access_method": access_method,
            }

        if not isinstance(data, dict):
            return None

        table = data.get("table", {})
        rows = table.get("rows", [])
        if not rows:
            return None

        tabledap_row = None
        griddap_row = None

        for row in rows:
            if not isinstance(row, list) or len(row) < 2:
                continue
            dataset_id = ""
            row_url = ""
            for cell in row:
                cell_str = str(cell) if cell else ""
                if "/tabledap/" in cell_str or "/griddap/" in cell_str:
                    row_url = cell_str
                if isinstance(cell, str) and cell.strip() and not dataset_id:
                    dataset_id = cell.strip()
            dataset_id = self._normalize_dataset_id(dataset_id)
            if not dataset_id:
                continue
            if dataset_id.lower() in {"alldatasets", "allDatasets"}:
                continue

            if not row_url:
                continue

            if "/tabledap/" in row_url and tabledap_row is None:
                tabledap_row = row
            elif "/griddap/" in row_url and griddap_row is None:
                griddap_row = row

        dataset_row = tabledap_row or griddap_row or rows[0]
        if not dataset_row:
            return None

        row_url = ""
        dataset_id = ""
        for cell in dataset_row:
            cell_str = str(cell) if cell else ""
            if "/tabledap/" in cell_str or "/griddap/" in cell_str:
                row_url = cell_str
            if isinstance(cell, str) and cell.strip() and not dataset_id:
                dataset_id = cell.strip()
        dataset_id = self._normalize_dataset_id(dataset_id)

        if not dataset_id or not row_url:
            return None

        if "/tabledap/" in row_url:
            access_method = "tabledap"
        elif "/griddap/" in row_url:
            access_method = "griddap"
        else:
            access_method = "tabledap"

        return {
            "dataset_id": dataset_id,
            "url": row_url,
            "access_method": access_method,
        }

    @staticmethod
    def _normalize_dataset_id(raw_id: str) -> str:
        raw_id = (raw_id or "").strip()
        if not raw_id:
            return ""
        if "/" in raw_id:
            raw_id = raw_id.rstrip("/").split("/")[-1]
        return raw_id.replace(".html", "").replace(".json", "")

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

        rows: list[dict] = []
        column_names: list[str] = []
        column_units: dict[str, str] = {}

        if isinstance(raw, dict):
            if "table" in raw:
                table = raw["table"]
                if "columnNames" in table:
                    column_names = [str(c) for c in table["columnNames"]]
                elif "columns" in table:
                    column_names = [c.get("name", "") for c in table["columns"]]
                if "columnUnits" in table and isinstance(table["columnUnits"], list):
                    for idx, unit in enumerate(table["columnUnits"]):
                        if idx < len(column_names):
                            column_units[column_names[idx]] = str(unit) if unit else ""
                if "rows" in table:
                    rows = [dict(zip(column_names, row)) for row in table["rows"]]
            elif "data" in raw and "variables" in raw:
                variables = raw["variables"]
                data_rows = raw["data"]
                rows = [dict(zip(variables, row)) for row in data_rows]
                column_names = [str(v) for v in variables]
            else:
                errors.append(f"unexpected_erddap_payload_keys={list(raw.keys())[:5]}")
        elif isinstance(raw, list):
            rows = [dict(r) if isinstance(r, dict) else {} for r in raw]
        else:
            errors.append(f"unsupported_raw_type={type(raw).__name__}")

        if not rows and not errors:
            errors.append("no_rows_returned")

        SPATIAL_COLUMNS = {"latitude", "longitude", "lat", "lon", "LATITUDE", "LONGITUDE"}
        TIME_COLUMNS = {"time", "TIME", "date", "DATE"}

        for row in rows:
            if not isinstance(row, dict):
                continue

            time_str = None
            for key in TIME_COLUMNS:
                if key in row and row[key] is not None:
                    time_str = str(row[key])
                    break

            valid_time = None
            if time_str:
                try:
                    valid_time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                except Exception:
                    valid_time = datetime.utcnow()

            for col in column_names:
                if col in SPATIAL_COLUMNS or col in TIME_COLUMNS:
                    continue
                raw_value = row.get(col)
                if raw_value is None:
                    continue

                variable = variable_mapping.get(col.lower(), col.lower())
                unit = column_units.get(col, "")
                confidence = 0.9

                evidence.append(
                    ConnectorEvidence(
                        source="incois",
                        variable=variable,
                        value=raw_value,
                        unit=unit or None,
                        valid_time=valid_time,
                        confidence=confidence,
                        why_it_matters=WHY_IT_MATTERS.get(variable),
                        url_ref=f"{INCOIS_ERDDAP_BASE}/tabledap/unknown.html",
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

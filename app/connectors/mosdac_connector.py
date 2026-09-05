"""
MOSDAC connector abstraction.

VERIFIED INTERFACE:
- MOSDAC Data Download API documented at:
  https://www.mosdac.gov.in/downloadapi-manual
  https://www.mosdac.gov.in/sites/default/files/docs/MOSDAC_Satellite_Data_Download_API.pdf

AUTHENTICATION:
- Username/password required for data download.
- Account registration and approval required.
- Search/preview may be possible without auth for some datasets, but
  actual data retrieval requires authenticated session.

RATE LIMITS:
- Daily download limit: 5000 files per user per day.
- Account locks for 1 hour after 3 consecutive failed login attempts.

CONFIGURATION:
- MOSDAC_USERNAME: MOSDAC account username
- MOSDAC_PASSWORD: MOSDAC account password
- MOSDAC_BASE_URL: Default "https://www.mosdac.gov.in"

NOTE:
- The MOSDAC API is designed for bulk file downloads (HDF5, netCDF, GeoTIFF).
- It is NOT a real-time REST API for individual observation queries.
- This connector implements the search and metadata portions.
- Actual satellite product ingestion would require file parsing (HDF5/netCDF)
  and is out of scope for Milestone 7 unless specific datasetIds are configured.
- Without valid credentials, the connector reports unavailable status.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from app.connectors.base_connector import BaseConnector, ConnectorEvidence, ConnectorResult
from app.config import settings

logger = logging.getLogger("orca")

MOSDAC_BASE_URL = "https://www.mosdac.gov.in"
MOSDAC_SEARCH_URL = f"{MOSDAC_BASE_URL}/catalog-app/satellite.php"
MOSDAC_THREDDS_CATALOG = "https://mosdac.gov.in/thredds/catalog.html"
MOSDAC_OPEN_DATA = "https://mosdac.gov.in/open-data"

WHY_IT_MATTERS = {
    "sst": "Sea surface temperature from satellite sensors indicates ocean thermal structure.",
    "sea_surface_temperature": "Sea surface temperature from satellite sensors indicates ocean thermal structure.",
    "chlorophyll": "Chlorophyll concentration indicates phytoplankton biomass and potential fishing zones.",
    "aod": "Aerosol optical depth indicates atmospheric particulate loading.",
    "lst": "Land surface temperature from thermal infrared sensors.",
    "rainfall": "Satellite-derived rainfall estimates support weather and flood monitoring.",
    "wind_speed": "Satellite scatterometer wind speed data.",
    "wind_direction": "Satellite-derived wind direction vectors.",
}


class MosdacConnector(BaseConnector):
    def __init__(
        self,
        base_url: str = MOSDAC_BASE_URL,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        super().__init__(base_url=base_url)
        self.username = username or getattr(settings, "MOSDAC_USERNAME", "") or ""
        self.password = password or getattr(settings, "MOSDAC_PASSWORD", "") or ""
        self._session_cookie: str | None = None

    async def _fetch_data(self, **kwargs: Any) -> Any:
        if not self.username or not self.password:
            raise RuntimeError("MOSDAC credentials are not configured")

        import httpx

        login_url = f"{self.base_url}/login"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            login_resp = await client.post(
                login_url,
                data={"username": self.username, "password": self.password},
            )
            login_resp.raise_for_status()
            self._session_cookie = login_resp.headers.get("set-cookie", "")

            search_url = f"{self.base_url}/catalog-app/api/search"
            params = {
                "datasetId": kwargs.get("datasetId", ""),
                "startTime": kwargs.get("startTime", ""),
                "endTime": kwargs.get("endTime", ""),
                "boundingBox": kwargs.get("boundingBox", ""),
                "count": min(int(kwargs.get("count", 10)), 100),
            }
            resp = await client.get(search_url, params=params, cookies=login_resp.cookies)
            resp.raise_for_status()
            return resp.json()

    async def search_datasets(self, query: str) -> ConnectorResult:
        try:
            import httpx

            url = f"{MOSDAC_SEARCH_URL}"
            params = {"search": query}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                return ConnectorResult(
                    status="success",
                    data={"html": resp.text, "query": query},
                    source_status="live",
                    retrieved_at=datetime.utcnow(),
                )
        except Exception as exc:
            logger.warning("MOSDAC dataset search failed: %s", exc)
            return ConnectorResult(
                status="error",
                errors=[f"mosdac_search_failed:{exc}"],
                source_status="unavailable",
                retrieved_at=datetime.utcnow(),
            )

    def normalize_sst(self, raw: Any) -> ConnectorResult:
        return self._normalize_generic(
            raw, variable="sst", unit="celsius", why="Sea surface temperature indicates ocean thermal structure."
        )

    def normalize_chlorophyll(self, raw: Any) -> ConnectorResult:
        return self._normalize_generic(
            raw, variable="chlorophyll", unit="mg/m3", why="Chlorophyll indicates phytoplankton concentration."
        )

    def _normalize_generic(
        self,
        raw: Any,
        variable: str,
        unit: str,
        why: str,
    ) -> ConnectorResult:
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
            if "results" in raw and isinstance(raw["results"], list):
                rows = raw["results"]
            elif "data" in raw and isinstance(raw["data"], list):
                rows = raw["data"]
            else:
                errors.append(f"unexpected_payload_keys={list(raw.keys())[:5]}")
        else:
            errors.append(f"unsupported_raw_type={type(raw).__name__}")

        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get("value") or row.get("magnitude") or row.get("data_value")
            time_str = row.get("time") or row.get("date") or row.get("startTime")
            lat = row.get("latitude") or row.get("lat")
            lon = row.get("longitude") or row.get("lon")

            if value is None:
                errors.append(f"missing_value_for_variable={variable}")
                continue

            valid_time = None
            if time_str:
                try:
                    valid_time = datetime.fromisoformat(str(time_str).replace("Z", "+00:00"))
                except Exception:
                    valid_time = datetime.utcnow()

            confidence = row.get("confidence") or row.get("qc_flag") or 0.8
            if not isinstance(confidence, (int, float)):
                confidence = 0.8

            url_ref = MOSDAC_THREDDS_CATALOG
            if row.get("datasetId") or row.get("dataset_id"):
                url_ref = f"{MOSDAC_BASE_URL}/dataset/" + str(row.get("datasetId") or row.get("dataset_id"))

            evidence.append(
                ConnectorEvidence(
                    source="mosdac",
                    variable=variable,
                    value=value,
                    unit=unit,
                    valid_time=valid_time,
                    confidence=confidence,
                    why_it_matters=why,
                    url_ref=url_ref,
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

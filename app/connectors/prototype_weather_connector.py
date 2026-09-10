"""
PROTOTYPE-ONLY fallback weather connector.

This connector is a TEMPORARY prototype fallback for the ORCA demo. It is NOT
an official IMD or INCOIS integration. When official API authorization is
available, this connector should be removed.

It calls a configurable third-party weather REST API and normalizes the
response into the standard ConnectorResult / ConnectorEvidence schema.

Required configuration (environment variables):
- PROTOTYPE_WEATHER_API_URL: base URL of the third-party weather API.
  The string "{lat}" and "{lon}" will be substituted with query coordinates.
- PROTOTYPE_WEATHER_API_KEY: optional bearer/key used in the Authorization
  header. Leave empty if the API does not require authentication.

All evidence returned by this connector carries:
- source="prototype_weather"
- source_status="prototype"
- confidence=0.5

This ensures the data is NEVER presented as official IMD or INCOIS data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from app.config import settings
from app.connectors.base_connector import BaseConnector, ConnectorEvidence, ConnectorResult

logger = logging.getLogger("orca")

VARIABLE_ALIASES: dict[str, str] = {
    "temp_c": "air_temperature",
    "temperature": "air_temperature",
    "temp": "air_temperature",
    "air_temperature": "air_temperature",
    "humidity": "humidity",
    "rel_humidity": "humidity",
    "wind_speed": "wind_speed",
    "wind_kph": "wind_speed",
    "wind_kph_2m": "wind_speed",
    "wind_mph": "wind_speed",
    "wind_gust": "wind_speed",
    "wind_dir": "wind_direction",
    "wind_direction": "wind_direction",
    "wind_degree": "wind_direction",
    "winddeg": "wind_direction",
    "sst": "sst",
    "sea_surface_temperature": "sst",
    "wave_height": "wave_height",
    "significant_wave_height": "wave_height",
    "swell_height": "swell_height",
}

WHY_IT_MATTERS = {
    "sst": "Sea surface temperature affects fish distribution and storm intensity.",
    "air_temperature": "Air temperature affects crew comfort and equipment performance.",
    "humidity": "Humidity affects weather patterns and storm development.",
    "wind_speed": "Wind speed affects sea state and vessel handling.",
    "wind_direction": "Wind direction influences wave patterns and drift.",
    "wave_height": "Wave height directly impacts vessel safety and fishing operations.",
    "swell_height": "Swell height contributes to overall sea state and vessel safety.",
}


class PrototypeWeatherConnector(BaseConnector):
    """Prototype-only weather connector. Not an official IMD or INCOIS integration."""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        timeout: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        effective_url = base_url or getattr(settings, "PROTOTYPE_WEATHER_API_URL", "") or ""
        super().__init__(base_url=effective_url or "https://example.com", timeout=timeout, max_retries=max_retries)
        self._api_key = api_key or getattr(settings, "PROTOTYPE_WEATHER_API_KEY", "") or ""

    async def _fetch_data(self, lat: float, lon: float, **kwargs: Any) -> Any:
        if not self.base_url or self.base_url in {"https://example.com", ""}:
            raise RuntimeError("prototype_weather_not_configured: PROTOTYPE_WEATHER_API_URL is empty")

        url = self.base_url.replace("{lat}", str(lat)).replace("{lon}", str(lon))
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        import httpx

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

    def normalize(self, raw: Any, **kwargs: Any) -> ConnectorResult:
        evidence: list[ConnectorEvidence] = []
        errors: list[str] = []

        payload = raw if isinstance(raw, dict) else {}
        source = "prototype_weather"
        source_status = "prototype"
        retrieved_at = datetime.utcnow()

        candidate_fields: dict[str, Any] = {}

        if isinstance(payload, dict):
            for key, value in payload.items():
                candidate_fields[key.lower()] = value
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        candidate_fields[f"{key.lower()}.{sub_key.lower()}"] = sub_value

        for field_name, raw_value in candidate_fields.items():
            if raw_value is None:
                continue
            variable = VARIABLE_ALIASES.get(field_name)
            if variable is None:
                continue
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError):
                continue

            unit = "celsius" if variable == "air_temperature" else "degree_C" if variable == "sst" else "kt" if variable == "wind_speed" else "degrees" if variable == "wind_direction" else "m" if variable == "wave_height" else "%" if variable == "humidity" else None
            confidence = 0.5

            evidence.append(
                ConnectorEvidence(
                    source=source,
                    variable=variable,
                    value=numeric_value,
                    unit=unit,
                    valid_time=retrieved_at,
                    confidence=confidence,
                    why_it_matters=WHY_IT_MATTERS.get(variable),
                    url_ref=self.base_url,
                )
            )

        if not evidence:
            errors.append("prototype_weather_no_recognized_fields")

        status = "success" if evidence else "no_data"

        return ConnectorResult(
            status=status,
            data=payload if status == "success" else None,
            evidence=evidence,
            errors=errors,
            source_status=source_status if evidence else "no_data",
            retrieved_at=retrieved_at,
        )

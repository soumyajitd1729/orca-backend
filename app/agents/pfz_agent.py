from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.agents.base_agent import BaseAgent, AgentResult
from app.connectors.incois_connector import IncoisConnector
from app.resilience.cache import marine_cache
from app.schemas.agent import AgentEvidence, AgentResultData
from app.services import pfz_service
from app.config import settings

logger = logging.getLogger("orca")


def _pfz_cache_key(lat: float, lon: float, radius_km: float) -> str:
    return f"incois:pfz:{lat:.2f}:{lon:.2f}:{radius_km:.1f}"


class PFZAgent(BaseAgent):
    async def _execute(
        self,
        db,
        lat: float,
        lon: float,
        radius_km: float = 10.0,
    ) -> AgentResultData:
        task_id = uuid.uuid4()
        started_at = datetime.utcnow()
        errors: list[str] = []

        zones = []
        source_status = "no_data"

        try:
            zones = await pfz_service.get_pfz_zones(lat, lon, radius_km, db)
            if zones:
                is_demo = any(
                    getattr(zone, "source_type", None) == "DEMO_SIMULATED"
                    for zone in zones
                )
                source_status = "demo" if is_demo else "live"
                try:
                    serialized = []
                    for zone in zones:
                        if hasattr(zone, "model_dump"):
                            serialized.append(zone.model_dump())
                        elif hasattr(zone, "__table__"):
                            serialized.append(
                                {c.name: getattr(zone, c.name) for c in zone.__table__.columns}
                            )
                        else:
                            serialized.append(dict(zone))
                    await marine_cache.set(
                        _pfz_cache_key(lat, lon, radius_km),
                        serialized,
                        source="incois",
                        status="cached",
                        ttl_seconds=86400,
                    )
                except Exception as exc:
                    logger.warning("Failed to cache PFZ zones: %s", exc)
        except Exception as exc:
            logger.warning("PFZAgent failed to fetch PFZ zones: %s", exc)
            return AgentResultData(
                agent_name=self.name,
                task_id=str(task_id),
                status="unavailable",
                data=None,
                evidence=[],
                errors=[f"pfz_service_error: {exc}"],
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status="unavailable",
            )

        if not zones:
            try:
                cache_entry = await marine_cache.get_entry(_pfz_cache_key(lat, lon, radius_km))
                if cache_entry is not None and isinstance(cache_entry.value, list) and cache_entry.value:
                    zones = cache_entry.value
                    age_seconds = (datetime.now(timezone.utc) - cache_entry.created_at).total_seconds()
                    if age_seconds > settings.CACHE_STALE_THRESHOLD_SECONDS:
                        source_status = "stale"
                        errors.append("pfz_data_stale")
                    else:
                        source_status = "cached"
            except Exception as exc:
                logger.warning("Failed to retrieve cached PFZ zones: %s", exc)

        if not zones:
            return AgentResultData(
                agent_name=self.name,
                task_id=str(task_id),
                status="no_data",
                data=[],
                evidence=[],
                errors=errors,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status=source_status,
            )

        evidence: list[AgentEvidence] = []
        data: list[dict] = []

        for zone in zones:
            if hasattr(zone, "model_dump"):
                zone_dict = zone.model_dump()
            elif hasattr(zone, "__table__"):
                zone_dict = {c.name: getattr(zone, c.name) for c in zone.__table__.columns}
            else:
                zone_dict = dict(zone)
            data.append(zone_dict)

            source_type = zone_dict.get("source_type", "")
            components = zone_dict.get("components") or {}
            pfz_class = components.get("pfz_class", "Unknown")
            pfz_probability = components.get("pfz_probability")

            if source_type == "DEMO_SIMULATED":
                advisory_label = f"Demo PFZ ({pfz_class})"
            else:
                advisory_label = zone_dict.get("sector") or zone_dict.get("landing_center") or "INCOIS PFZ advisory"

            valid_time = zone_dict.get("valid_time")
            forecast_date = zone_dict.get("forecast_date")
            valid_until = zone_dict.get("valid_until")
            validity_parts = []
            if forecast_date:
                validity_parts.append(f"forecast {forecast_date}")
            if valid_until:
                validity_parts.append(f"valid until {valid_until}")
            validity_text = ", ".join(validity_parts) if validity_parts else "validity unknown"

            if source_type == "DEMO_SIMULATED":
                probability_text = (
                    f" Synthetic PFZ probability: {pfz_probability:.3f}."
                    if pfz_probability is not None
                    else ""
                )
                why_it_matters = (
                    f"DEMO PFZ DATA — SYNTHETIC / NOT LIVE INCOIS DATA. "
                    f"Classification: {pfz_class}.{probability_text} "
                    f"Depth: {zone_dict.get('depth') or 'N/A'}. "
                    f"Distance from coast: {zone_dict.get('distance_km') or 'N/A'} km. "
                    f"{validity_text}."
                ).strip()
            else:
                why_it_matters = (
                    f"INCOIS PFZ advisory for {advisory_label}. "
                    f"Depth: {zone_dict.get('depth') or 'N/A'}. "
                    f"Location context: {zone_dict.get('distance_km') or 'N/A'} km {zone_dict.get('direction') or ''} from {zone_dict.get('landing_center') or 'reference point'}. "
                    f"{validity_text}."
                ).strip()

            evidence.append(
                AgentEvidence(
                    source=zone_dict.get("source_name", source_type or "incois"),
                    variable="pfz_advisory",
                    value=advisory_label,
                    unit="advisory",
                    valid_time=valid_time,
                    confidence=None,
                    why_it_matters=why_it_matters,
                    url_ref=(
                        "https://incois.gov.in/MarineFisheries/PfzAdvisory"
                        if source_type != "DEMO_SIMULATED"
                        else None
                    ),
                )
            )

        completed_at = datetime.utcnow()
        duration_ms = (completed_at - started_at).total_seconds() * 1000

        return AgentResultData(
            agent_name=self.name,
            task_id=str(task_id),
            status="success",
            data=data,
            evidence=evidence,
            errors=errors,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 3),
            source_status=source_status,
        )

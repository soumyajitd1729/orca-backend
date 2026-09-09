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
                source_status = "live"
                try:
                    await marine_cache.set(
                        _pfz_cache_key(lat, lon, radius_km),
                        [
                            zone.model_dump() if hasattr(zone, "model_dump") else dict(zone)
                            for zone in zones
                        ],
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
            zone_dict = zone.model_dump() if hasattr(zone, "model_dump") else dict(zone)
            evidence.append(
                AgentEvidence(
                    source="incois",
                    variable="pfz_score",
                    value=zone_dict.get("score"),
                    unit="index",
                    valid_time=zone_dict.get("valid_time"),
                    confidence=zone_dict.get("score"),
                    why_it_matters="Potential Fishing Zone score indicates oceanographic conditions favorable for fish aggregation.",
                )
            )
            data.append(zone_dict)

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

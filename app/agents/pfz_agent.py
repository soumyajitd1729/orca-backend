from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from app.agents.base_agent import BaseAgent, AgentResult
from app.schemas.agent import AgentEvidence, AgentResultData
from app.services import pfz_service

logger = logging.getLogger("orca")


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

        try:
            zones = await pfz_service.get_pfz_zones(lat, lon, radius_km, db)
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
            return AgentResultData(
                agent_name=self.name,
                task_id=str(task_id),
                status="no_data",
                data=[],
                evidence=[],
                errors=[],
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status="no_data",
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
            source_status="live",
        )

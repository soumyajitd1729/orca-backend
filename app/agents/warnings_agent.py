from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from app.agents.base_agent import BaseAgent, AgentResult
from app.schemas.agent import AgentEvidence, AgentResultData
from app.services import warnings_service

logger = logging.getLogger("orca")


class WarningsAgent(BaseAgent):
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
            warnings = await warnings_service.get_active_warnings_within_radius(
                lat, lon, radius_km, db
            )
        except Exception as exc:
            logger.warning("WarningsAgent failed to fetch warnings: %s", exc)
            return AgentResultData(
                agent_name=self.name,
                task_id=str(task_id),
                status="unavailable",
                data=None,
                evidence=[],
                errors=[f"warnings_service_error: {exc}"],
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status="unavailable",
            )

        if not warnings:
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

        for warning in warnings:
            warning_dict = warning.model_dump() if hasattr(warning, "model_dump") else dict(warning)
            evidence.append(
                AgentEvidence(
                    source=warning_dict.get("issued_by", "unknown"),
                    variable="warning",
                    value=warning_dict.get("type"),
                    unit="advisory",
                    valid_time=warning_dict.get("valid_from"),
                    confidence=1.0,
                    why_it_matters="Active marine warning affects safety assessment for the queried area.",
                    url_ref=None,
                )
            )
            data.append(warning_dict)

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

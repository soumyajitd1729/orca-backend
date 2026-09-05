from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from app.agents.base_agent import BaseAgent, AgentResult
from app.schemas.agent import AgentEvidence, AgentResultData
from app.services import route_service

logger = logging.getLogger("orca")


class RouteAgent(BaseAgent):
    async def _execute(
        self,
        db,
        waypoints: list[dict],
        vessel_type: Optional[str] = None,
        max_wave_height: Optional[float] = None,
    ) -> AgentResultData:
        task_id = uuid.uuid4()
        started_at = datetime.utcnow()
        errors: list[str] = []

        if not waypoints or len(waypoints) < 2:
            return AgentResultData(
                agent_name=self.name,
                task_id=str(task_id),
                status="error",
                data=None,
                evidence=[],
                errors=["At least two waypoints are required for route evaluation"],
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status="error",
            )

        try:
            evaluation = await route_service.evaluate_route(
                db, waypoints, vessel_type, max_wave_height
            )
        except Exception as exc:
            logger.warning("RouteAgent failed to evaluate route: %s", exc)
            return AgentResultData(
                agent_name=self.name,
                task_id=str(task_id),
                status="unavailable",
                data=None,
                evidence=[],
                errors=[f"route_service_error: {exc}"],
                started_at=started_at,
                completed_at=datetime.utcnow(),
                duration_ms=0.0,
                source_status="unavailable",
            )

        evidence: list[AgentEvidence] = []
        data: dict = {}

        if hasattr(evaluation, "model_dump"):
            data = evaluation.model_dump()
        else:
            data = dict(evaluation)

        evidence.append(
            AgentEvidence(
                source="orca_route_service",
                variable="route_cost",
                value=data.get("route_cost"),
                unit="km",
                why_it_matters="Total route distance in kilometers.",
            )
        )

        risk_level = data.get("risk_level")
        if risk_level:
            evidence.append(
                AgentEvidence(
                    source="orca_route_service",
                    variable="risk_level",
                    value=risk_level,
                    unit="category",
                    why_it_matters="Deterministic risk level computed from geofence violations and hazard warnings.",
                )
            )

        geofence_violations = data.get("geofence_violations", [])
        if geofence_violations:
            evidence.append(
                AgentEvidence(
                    source="orca_route_service",
                    variable="geofence_violations",
                    value=len(geofence_violations),
                    unit="count",
                    why_it_matters="Number of Marine Protected Area boundaries intersected by the route.",
                )
            )

        hazard_warnings = data.get("hazard_warnings", [])
        if hazard_warnings:
            evidence.append(
                AgentEvidence(
                    source="orca_route_service",
                    variable="hazard_warnings",
                    value=len(hazard_warnings),
                    unit="count",
                    why_it_matters="Number of active warnings near route waypoints.",
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
            source_status="live",
        )

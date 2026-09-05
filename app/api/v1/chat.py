from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from typing import List, Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.agents.intent_agent import IntentAgent
from app.db.session import get_db
from app.envelope import build_envelope
from app.orchestration.orchestrator import Orchestrator
from app.schemas.agent import (
    AgentEvidence,
    AgentTraceEntry,
    NormalizedIntent,
    OrchestrationContext,
)

logger = logging.getLogger("orca")
router = APIRouter()


class UserLocation(BaseModel):
    lat: float
    lon: float


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    language: str = Field(default="en", pattern="^(en|hi|te)$")
    user_location: Optional[UserLocation] = None


class EvidenceCard(BaseModel):
    source: str
    url: Optional[str] = None
    snippet: str


@router.post("/chat")
async def chat_orchestration(
    payload: ChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    context = OrchestrationContext(
        conversation_id=payload.conversation_id,
        user_message=payload.message,
        language=payload.language,
        user_location=None,
        user_lat=payload.user_location.lat if payload.user_location else None,
        user_lon=payload.user_location.lon if payload.user_location else None,
        requested_radius_km=25.0,
        route_waypoints=None,
        vessel_type=None,
        max_wave_height=None,
        db=db,
        normalized_intent=None,
    )

    intent_agent = IntentAgent(name="intent")
    intent_result = await intent_agent.run(
        message=payload.message,
        user_location=context.user_location,
        user_lat=context.user_lat,
        user_lon=context.user_lon,
        requested_radius_km=context.requested_radius_km,
    )
    intent_data = intent_result.result.data if intent_result.result and hasattr(intent_result.result, "data") else {}
    if not isinstance(intent_data, dict):
        intent_data = {}

    intent = NormalizedIntent(
        query_type=intent_data.get("query_type", "general"),
        location_name=context.user_location,
        latitude=context.user_lat,
        longitude=context.user_lon,
        language=payload.language,
        requested_radius_km=context.requested_radius_km,
        raw_message=payload.message,
    )

    orchestrator = Orchestrator(db=db, context=context)
    orchestration_result = await orchestrator.execute(intent)

    safety_result = orchestration_result.safety_result or {}
    synthesis = orchestration_result.synthesis_result or {}
    synthesis_data = synthesis.get("data", synthesis) if isinstance(synthesis, dict) else {}

    safety_badge = safety_result.get("safety_badge")
    if safety_badge is None:
        safety_badge = synthesis_data.get("safety_badge")

    evidence_cards = []
    for evidence in orchestration_result.aggregated_evidence:
        evidence_cards.append(
            {
                "source": evidence.source,
                "url": evidence.url_ref,
                "snippet": f"{evidence.variable}: {evidence.value} {evidence.unit or ''}".strip(),
            }
        )

    warnings_list = []
    for r in orchestration_result.agent_results:
        agent_name = r.get("agent_name") if isinstance(r, dict) else getattr(r, "agent_name", None)
        if agent_name == "WarningsAgent":
            raw_warnings = r.get("data") if isinstance(r, dict) else getattr(r, "data", None)
            if isinstance(raw_warnings, list):
                warnings_list = [w for w in raw_warnings if isinstance(w, dict)]
            break

    def _to_iso(val):
        if val is None:
            return None
        if isinstance(val, str):
            return val
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return str(val)

    agent_trace = []
    for trace in orchestration_result.agent_trace:
        agent_trace.append(
            {
                "agent_name": trace.get("agent_name") if isinstance(trace, dict) else getattr(trace, "agent_name", None),
                "status": trace.get("status") if isinstance(trace, dict) else getattr(trace, "status", None),
                "task_id": trace.get("task_id") if isinstance(trace, dict) else getattr(trace, "task_id", None),
                "started_at": _to_iso(trace.get("started_at") if isinstance(trace, dict) else getattr(trace, "started_at", None)),
                "completed_at": _to_iso(trace.get("completed_at") if isinstance(trace, dict) else getattr(trace, "completed_at", None)),
                "duration_ms": trace.get("duration_ms") if isinstance(trace, dict) else getattr(trace, "duration_ms", None),
                "dependencies": trace.get("dependencies") if isinstance(trace, dict) else getattr(trace, "dependencies", []),
                "error": trace.get("error") if isinstance(trace, dict) else getattr(trace, "error", None),
            }
        )

    map_layers = []
    for evidence in orchestration_result.aggregated_evidence:
        if evidence.source == "orca_route_service" and evidence.variable == "route_cost":
            map_layers.append(
                {
                    "layer_type": "route",
                    "route_cost": evidence.value,
                    "unit": evidence.unit,
                }
            )
        elif evidence.source == "incois" and evidence.variable == "pfz_score":
            map_layers.append(
                {
                    "layer_type": "pfz_zones",
                    "score": evidence.value,
                    "unit": evidence.unit,
                    "valid_time": evidence.valid_time.isoformat() if evidence.valid_time else None,
                }
            )

    answer = synthesis_data.get("answer", "")
    if not answer and orchestration_result.overall_status in ("timeout", "error"):
        answer = "The orchestration pipeline encountered an issue. Current safety cannot be confirmed due to insufficient or unavailable data."
    elif not answer:
        answer = "Current safety cannot be confirmed because required marine data is unavailable."

    follow_up_suggestions = synthesis_data.get("follow_up_suggestions", [])

    response_data = {
        "conversation_id": payload.conversation_id or f"conv_{orchestration_result.task_id}",
        "answer": answer,
        "safety_badge": safety_badge,
        "evidence_cards": evidence_cards,
        "map_layers": map_layers,
        "agent_trace": agent_trace,
        "warnings": warnings_list,
        "follow_up_suggestions": follow_up_suggestions,
    }

    return build_envelope(data=response_data)

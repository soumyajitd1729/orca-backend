from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field


class AgentEvidence(BaseModel):
    source: str
    variable: str
    value: Any
    unit: Optional[str] = None
    valid_time: Optional[datetime] = None
    confidence: Optional[float] = None
    why_it_matters: Optional[str] = None
    url_ref: Optional[str] = None


class AgentResultData(BaseModel):
    agent_name: str
    task_id: Optional[str] = None
    status: str
    data: Optional[Any] = None
    evidence: list[AgentEvidence] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    source_status: Optional[str] = None


class NormalizedIntent(BaseModel):
    query_type: str = "general"
    location_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    time_expression: Optional[str] = None
    normalized_time: Optional[str] = None
    language: str = "en"
    requested_radius_km: Optional[float] = None
    route_start: Optional[dict] = None
    route_end: Optional[dict] = None
    weather_intent: bool = False
    pfz_intent: bool = False
    warning_intent: bool = False
    route_intent: bool = False
    raw_message: Optional[str] = None


class PlanStep(BaseModel):
    agent_name: str
    depends_on: list[str] = Field(default_factory=list)
    input_mapping: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(BaseModel):
    steps: list[PlanStep] = Field(default_factory=list)
    max_depth: int = 4
    estimated_duration_ms: Optional[float] = None
    requires_safety_evaluation: bool = False


class SynthesisResponse(BaseModel):
    answer: str
    follow_up_suggestions: list[str] = Field(default_factory=list)
    language: str = "en"
    evidence_summary: list[dict] = Field(default_factory=list)
    safety_badge: Optional[str] = None
    fishing_suitability: Optional[str] = None


class OrchestrationContext(BaseModel):
    conversation_id: Optional[str] = None
    user_message: str
    language: str = "en"
    user_location: Optional[str] = None
    user_lat: Optional[float] = None
    user_lon: Optional[float] = None
    requested_radius_km: Optional[float] = None
    route_waypoints: Optional[list[dict]] = None
    vessel_type: Optional[str] = None
    max_wave_height: Optional[float] = None
    db: Any = None
    normalized_intent: Optional[NormalizedIntent] = None


class AgentTraceEntry(BaseModel):
    agent_name: str
    status: str
    task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    dependencies: list[str] = Field(default_factory=list)
    error: Optional[str] = None


class OrchestrationResult(BaseModel):
    task_id: str
    intent: NormalizedIntent
    plan: ExecutionPlan
    agent_results: list[AgentResultData] = Field(default_factory=list)
    agent_trace: list[AgentTraceEntry] = Field(default_factory=list)
    aggregated_evidence: list[AgentEvidence] = Field(default_factory=list)
    safety_result: Optional[dict] = None
    validation_result: Optional[dict] = None
    synthesis_result: Optional[dict] = None
    errors: list[str] = Field(default_factory=list)
    overall_status: str = "success"

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.agents.base_agent import AgentResult
from app.orchestration.orchestrator import Orchestrator
from app.schemas.agent import (
    AgentEvidence,
    AgentResultData,
    NormalizedIntent,
    OrchestrationContext,
    PlanStep,
)


def _make_context(**overrides):
    defaults = dict(
        conversation_id=None,
        user_message="What are the warnings?",
        language="en",
        user_location="Kakinada",
        user_lat=16.9891,
        user_lon=82.2475,
        requested_radius_km=25.0,
        route_waypoints=None,
        vessel_type=None,
        max_wave_height=None,
        db=AsyncMock(),
        normalized_intent=None,
    )
    defaults.update(overrides)
    return OrchestrationContext(**defaults)


def _intent_result(latitude=16.9891, longitude=82.2475, query_type="warnings"):
    return AgentResult(
        status="success",
        result=AgentResultData(
            agent_name="intent",
            task_id="intent-1",
            status="success",
            data={
                "query_type": query_type,
                "location_name": "Kakinada",
                "latitude": latitude,
                "longitude": longitude,
                "time_expression": None,
                "language": "en",
                "requested_radius_km": 25.0,
                "route_start": None,
                "route_end": None,
                "weather_intent": False,
                "pfz_intent": False,
                "warning_intent": True,
                "route_intent": False,
                "intents": ["warnings"],
                "raw_message": "What are the warnings?",
            },
            evidence=[],
            errors=[],
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_ms=100.0,
            source_status="llm",
        ),
        attempts=1,
    )


def _agent_data_result(data, agent_name="test"):
    return AgentResult(
        status="success",
        result=AgentResultData(
            agent_name=agent_name,
            task_id=f"{agent_name}-1",
            status="success",
            data=data,
            evidence=[],
            errors=[],
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_ms=50.0,
            source_status="live",
        ),
        attempts=1,
    )


class FakeAgent:
    def __init__(self, name, coroutine):
        self.name = name
        self._coroutine = coroutine

    async def run(self, *args, **kwargs):
        return await self._coroutine(*args, **kwargs)


class FakeSafetyEngine:
    @staticmethod
    def evaluate(**kwargs):
        class FakeSafety:
            safety_badge = "SAFE"
            hazard_breakdown = None
            fishing_suitability = None
            is_indeterminate = False
            reasons = []
        return FakeSafety()


class FakeEvidenceValidator:
    @staticmethod
    def validate(claims, evidence):
        class FakeValidation:
            is_valid = True
            supported_claims = []
            unsupported_claims = []
            issues = []
            overall_confidence = 1.0
        return FakeValidation()


@pytest.mark.asyncio
async def test_simple_warning_plan(monkeypatch):
    context = _make_context(user_message="What are the warnings?", query_type="warnings")

    async def fake_intent_run(**kwargs):
        return _intent_result(query_type="warnings")

    async def fake_warnings_run(**kwargs):
        return _agent_data_result([{"type": "cyclone", "severity": "high"}], "warnings")

    async def fake_synthesizer_run(**kwargs):
        return AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "test"}, evidence=[], errors=[]), attempts=1)

    monkeypatch.setattr("app.orchestration.orchestrator.IntentAgent", lambda name: FakeAgent(name, fake_intent_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WarningsAgent", lambda name: FakeAgent(name, fake_warnings_run))
    monkeypatch.setattr("app.orchestration.orchestrator.SafetyEngine", FakeSafetyEngine)
    monkeypatch.setattr("app.orchestration.orchestrator.EvidenceValidator", FakeEvidenceValidator)
    monkeypatch.setattr("app.orchestration.orchestrator.ResponseSynthesizer", lambda name: FakeAgent(name, fake_synthesizer_run))

    orchestrator = Orchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="warnings")
    result = await orchestrator.execute(intent)

    assert result.overall_status == "success"
    agent_names = [r.agent_name for r in result.agent_results]
    assert "WarningsAgent" in agent_names
    assert "SafetyEngine" in agent_names
    assert "EvidenceValidator" in agent_names
    assert "ResponseSynthesizer" in agent_names


@pytest.mark.asyncio
async def test_independent_agents_execute_concurrently(monkeypatch):
    context = _make_context(user_message="Is it safe to fish?", query_type="fishing")

    execution_order = []

    async def fake_intent_run(**kwargs):
        execution_order.append("intent")
        return _intent_result(query_type="fishing")

    async def fake_weather_run(**kwargs):
        await asyncio.sleep(0.01)
        execution_order.append("weather")
        return _agent_data_result([{"variable": "wave_height", "value": 1.0}], "weather")

    async def fake_pfz_run(**kwargs):
        await asyncio.sleep(0.01)
        execution_order.append("pfz")
        return _agent_data_result([{"score": 0.8}], "pfz")

    async def fake_warnings_run(**kwargs):
        await asyncio.sleep(0.01)
        execution_order.append("warnings")
        return _agent_data_result([], "warnings")

    async def fake_synthesizer_run(**kwargs):
        execution_order.append("synthesizer")
        return AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "test"}, evidence=[], errors=[]), attempts=1)

    monkeypatch.setattr("app.orchestration.orchestrator.IntentAgent", lambda name: FakeAgent(name, fake_intent_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WeatherAgent", lambda name: FakeAgent(name, fake_weather_run))
    monkeypatch.setattr("app.orchestration.orchestrator.PFZAgent", lambda name: FakeAgent(name, fake_pfz_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WarningsAgent", lambda name: FakeAgent(name, fake_warnings_run))
    monkeypatch.setattr("app.orchestration.orchestrator.SafetyEngine", FakeSafetyEngine)
    monkeypatch.setattr("app.orchestration.orchestrator.EvidenceValidator", FakeEvidenceValidator)
    monkeypatch.setattr("app.orchestration.orchestrator.ResponseSynthesizer", lambda name: FakeAgent(name, fake_synthesizer_run))

    orchestrator = Orchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="fishing")
    result = await orchestrator.execute(intent)

    assert result.overall_status == "success"
    assert execution_order.index("weather") < execution_order.index("synthesizer")
    assert execution_order.index("pfz") < execution_order.index("synthesizer")
    assert execution_order.index("warnings") < execution_order.index("synthesizer")


@pytest.mark.asyncio
async def test_dependency_ordering(monkeypatch):
    context = _make_context(user_message="Is it safe to fish?", query_type="fishing")

    execution_order = []

    async def fake_intent_run(**kwargs):
        execution_order.append("intent")
        return _intent_result(query_type="fishing")

    async def fake_weather_run(**kwargs):
        execution_order.append("weather")
        return _agent_data_result([], "weather")

    async def fake_pfz_run(**kwargs):
        execution_order.append("pfz")
        return _agent_data_result([], "pfz")

    async def fake_warnings_run(**kwargs):
        execution_order.append("warnings")
        return _agent_data_result([], "warnings")

    async def fake_synthesizer_run(**kwargs):
        execution_order.append("synthesizer")
        return AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "test"}, evidence=[], errors=[]), attempts=1)

    monkeypatch.setattr("app.orchestration.orchestrator.IntentAgent", lambda name: FakeAgent(name, fake_intent_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WeatherAgent", lambda name: FakeAgent(name, fake_weather_run))
    monkeypatch.setattr("app.orchestration.orchestrator.PFZAgent", lambda name: FakeAgent(name, fake_pfz_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WarningsAgent", lambda name: FakeAgent(name, fake_warnings_run))
    monkeypatch.setattr("app.orchestration.orchestrator.SafetyEngine", FakeSafetyEngine)
    monkeypatch.setattr("app.orchestration.orchestrator.EvidenceValidator", FakeEvidenceValidator)
    monkeypatch.setattr("app.orchestration.orchestrator.ResponseSynthesizer", lambda name: FakeAgent(name, fake_synthesizer_run))

    orchestrator = Orchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="fishing")
    result = await orchestrator.execute(intent)

    assert execution_order.index("intent") < execution_order.index("weather")
    assert execution_order.index("intent") < execution_order.index("pfz")
    assert execution_order.index("intent") < execution_order.index("warnings")
    assert execution_order.index("weather") < execution_order.index("synthesizer")
    assert execution_order.index("pfz") < execution_order.index("synthesizer")
    assert execution_order.index("warnings") < execution_order.index("synthesizer")


@pytest.mark.asyncio
async def test_circular_dependency_rejection():
    plan = type("Plan", (), {"steps": [
        PlanStep(agent_name="IntentAgent", depends_on=["ResponseSynthesizer"]),
        PlanStep(agent_name="ResponseSynthesizer", depends_on=["IntentAgent"]),
    ]})()
    context = _make_context()
    orchestrator = Orchestrator(db=context.db, context=context)
    with pytest.raises(ValueError, match="Circular dependency"):
        orchestrator._validate_plan(plan)


@pytest.mark.asyncio
async def test_unknown_agent_rejection():
    plan = type("Plan", (), {"steps": [PlanStep(agent_name="UnknownAgent", depends_on=[])]})()
    context = _make_context()
    orchestrator = Orchestrator(db=context.db, context=context)
    with pytest.raises(ValueError, match="Unknown agent"):
        await orchestrator._execute_plan(plan)


@pytest.mark.asyncio
async def test_timeout_handling():
    context = _make_context(user_message="What are the warnings?", query_type="warnings")

    class TimeoutOrchestrator(Orchestrator):
        async def _run_intent_agent(self):
            return AgentResult(status="timeout", error="timeout after 8.0s")

    orchestrator = TimeoutOrchestrator(db=context.db, context=context, max_concurrency=5)
    intent = NormalizedIntent(query_type="warnings")
    result = await orchestrator.execute(intent)

    assert result.overall_status == "timeout"
    assert any(trace.agent_name == "IntentAgent" and trace.status == "timeout" for trace in result.agent_trace)


@pytest.mark.asyncio
async def test_retry_behavior():
    context = _make_context(user_message="What are the warnings?", query_type="warnings")

    class FlakyOrchestrator(Orchestrator):
        async def _run_intent_agent(self):
            return _intent_result()

        async def _run_warnings_agent(self, deps):
            return _agent_data_result([], "warnings")

        def _run_safety_engine(self, deps):
            return AgentResult(status="success", result=type("Safety", (), {"safety_badge": "SAFE", "hazard_breakdown": None, "fishing_suitability": None, "is_indeterminate": False, "reasons": []})(), attempts=1)

        def _run_evidence_validator(self, deps):
            return AgentResult(status="success", result=type("Validation", (), {"is_valid": True, "supported_claims": [], "unsupported_claims": [], "issues": [], "overall_confidence": 1.0})(), attempts=1)

        async def _run_response_synthesizer(self, deps):
            return AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "test"}, evidence=[], errors=[]), attempts=1)

    orchestrator = FlakyOrchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="warnings")
    result = await orchestrator.execute(intent)
    assert result.overall_status == "success"


@pytest.mark.asyncio
async def test_partial_branch_failure(monkeypatch):
    context = _make_context(user_message="Is it safe to fish?", query_type="fishing")

    async def fake_intent_run(**kwargs):
        return _intent_result(query_type="fishing")

    async def fake_weather_run(**kwargs):
        return AgentResult(status="unavailable", error="DB down", attempts=1)

    async def fake_pfz_run(**kwargs):
        return _agent_data_result([{"score": 0.8}], "pfz")

    async def fake_warnings_run(**kwargs):
        return _agent_data_result([], "warnings")

    class FakeSafetyEnginePartial:
        @staticmethod
        def evaluate(**kwargs):
            class FakeSafety:
                safety_badge = "CAUTION"
                hazard_breakdown = type("HB", (), {"wave": None, "wind": None, "lightning": None, "geofence": None})()
                fishing_suitability = "FAIR"
                is_indeterminate = False
                reasons = ["weather unavailable"]
            return FakeSafety()

    monkeypatch.setattr("app.orchestration.orchestrator.IntentAgent", lambda name: FakeAgent(name, fake_intent_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WeatherAgent", lambda name: FakeAgent(name, fake_weather_run))
    monkeypatch.setattr("app.orchestration.orchestrator.PFZAgent", lambda name: FakeAgent(name, fake_pfz_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WarningsAgent", lambda name: FakeAgent(name, fake_warnings_run))
    monkeypatch.setattr("app.orchestration.orchestrator.SafetyEngine", FakeSafetyEnginePartial)
    monkeypatch.setattr("app.orchestration.orchestrator.EvidenceValidator", FakeEvidenceValidator)
    monkeypatch.setattr("app.orchestration.orchestrator.ResponseSynthesizer", lambda name: FakeAgent(name, lambda **kw: AgentResult(status="partial", result=AgentResultData(agent_name="synthesizer", status="partial", data={"answer": "Partial data"}, evidence=[], errors=["weather unavailable"]), attempts=1)))

    orchestrator = Orchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="fishing")
    result = await orchestrator.execute(intent)

    assert result.overall_status in ("success", "partial", "error")
    weather_results = [r for r in result.agent_results if r.agent_name == "WeatherAgent"]
    assert len(weather_results) == 1
    assert weather_results[0].status == "unavailable"
    pfz_results = [r for r in result.agent_results if r.agent_name == "PFZAgent"]
    assert len(pfz_results) == 1
    assert pfz_results[0].status == "success"


@pytest.mark.asyncio
async def test_safety_engine_cannot_be_bypassed(monkeypatch):
    context = _make_context(user_message="What are the warnings?", query_type="warnings")

    async def fake_intent_run(**kwargs):
        return _intent_result(query_type="warnings")

    async def fake_warnings_run(**kwargs):
        return _agent_data_result([{"type": "cyclone", "severity": "extreme", "issued_by": "IMD"}], "warnings")

    async def fake_synthesizer_run(**kwargs):
        return AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "test"}, evidence=[], errors=[]), attempts=1)

    monkeypatch.setattr("app.orchestration.orchestrator.IntentAgent", lambda name: FakeAgent(name, fake_intent_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WarningsAgent", lambda name: FakeAgent(name, fake_warnings_run))
    monkeypatch.setattr("app.orchestration.orchestrator.SafetyEngine", FakeSafetyEngine)
    monkeypatch.setattr("app.orchestration.orchestrator.EvidenceValidator", FakeEvidenceValidator)
    monkeypatch.setattr("app.orchestration.orchestrator.ResponseSynthesizer", lambda name: FakeAgent(name, fake_synthesizer_run))

    orchestrator = Orchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="warnings")
    result = await orchestrator.execute(intent)

    agent_names = [r.agent_name for r in result.agent_results]
    assert "SafetyEngine" in agent_names
    assert "EvidenceValidator" in agent_names
    assert "ResponseSynthesizer" in agent_names


@pytest.mark.asyncio
async def test_evidence_aggregation(monkeypatch):
    context = _make_context(user_message="Is it safe to fish?", query_type="fishing")

    async def fake_intent_run(**kwargs):
        return _intent_result(query_type="fishing")

    async def fake_weather_run(**kwargs):
        return _agent_data_result([{"variable": "wave_height", "value": 2.5, "unit": "m"}], "weather")

    async def fake_pfz_run(**kwargs):
        return _agent_data_result([{"score": 0.8}], "pfz")

    async def fake_warnings_run(**kwargs):
        return _agent_data_result([], "warnings")

    class FakeSafetyEngineWithEvidence:
        @staticmethod
        def evaluate(**kwargs):
            class FakeSafety:
                safety_badge = "SAFE"
                hazard_breakdown = type("HB", (), {"wave": 0.0, "wind": None, "lightning": 0.0, "geofence": 0.0})()
                fishing_suitability = "GOOD"
                is_indeterminate = False
                reasons = []
            return FakeSafety()

    monkeypatch.setattr("app.orchestration.orchestrator.IntentAgent", lambda name: FakeAgent(name, fake_intent_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WeatherAgent", lambda name: FakeAgent(name, fake_weather_run))
    monkeypatch.setattr("app.orchestration.orchestrator.PFZAgent", lambda name: FakeAgent(name, fake_pfz_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WarningsAgent", lambda name: FakeAgent(name, fake_warnings_run))
    monkeypatch.setattr("app.orchestration.orchestrator.SafetyEngine", FakeSafetyEngineWithEvidence)
    monkeypatch.setattr("app.orchestration.orchestrator.EvidenceValidator", FakeEvidenceValidator)
    monkeypatch.setattr("app.orchestration.orchestrator.ResponseSynthesizer", lambda name: FakeAgent(name, lambda **kw: AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "test"}, evidence=[], errors=[]), attempts=1)))

    orchestrator = Orchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="fishing")
    result = await orchestrator.execute(intent)

    assert len(result.aggregated_evidence) > 0
    sources = [e.source for e in result.aggregated_evidence]
    assert "safety_engine" in sources


@pytest.mark.asyncio
async def test_real_agent_trace(monkeypatch):
    context = _make_context(user_message="What are the warnings?", query_type="warnings")

    async def fake_intent_run(**kwargs):
        return _intent_result(query_type="warnings")

    async def fake_warnings_run(**kwargs):
        return _agent_data_result([{"type": "cyclone"}], "warnings")

    async def fake_synthesizer_run(**kwargs):
        return AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "test"}, evidence=[], errors=[]), attempts=1)

    monkeypatch.setattr("app.orchestration.orchestrator.IntentAgent", lambda name: FakeAgent(name, fake_intent_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WarningsAgent", lambda name: FakeAgent(name, fake_warnings_run))
    monkeypatch.setattr("app.orchestration.orchestrator.SafetyEngine", FakeSafetyEngine)
    monkeypatch.setattr("app.orchestration.orchestrator.EvidenceValidator", FakeEvidenceValidator)
    monkeypatch.setattr("app.orchestration.orchestrator.ResponseSynthesizer", lambda name: FakeAgent(name, fake_synthesizer_run))

    orchestrator = Orchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="warnings")
    result = await orchestrator.execute(intent)

    assert len(result.agent_trace) > 0
    trace_agents = [t.agent_name for t in result.agent_trace]
    assert "IntentAgent" in trace_agents
    assert "WarningsAgent" in trace_agents
    assert "SafetyEngine" in trace_agents
    assert "EvidenceValidator" in trace_agents
    assert "ResponseSynthesizer" in trace_agents

    for trace in result.agent_trace:
        assert trace.status in ("success", "timeout", "error")
        assert trace.started_at is not None
        assert trace.completed_at is not None
        assert trace.duration_ms is not None
        assert trace.dependencies is not None


@pytest.mark.asyncio
async def test_maximum_concurrency(monkeypatch):
    context = _make_context(user_message="Is it safe to fish?", query_type="fishing")

    async def fake_intent_run(**kwargs):
        return _intent_result(query_type="fishing")

    async def slow_agent(name, **kwargs):
        await asyncio.sleep(0.05)
        return _agent_data_result([], name)

    async def fake_synthesizer_run(**kwargs):
        return AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "test"}, evidence=[], errors=[]), attempts=1)

    monkeypatch.setattr("app.orchestration.orchestrator.IntentAgent", lambda name: FakeAgent(name, fake_intent_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WeatherAgent", lambda name: FakeAgent(name, lambda **kw: slow_agent("weather", **kw)))
    monkeypatch.setattr("app.orchestration.orchestrator.PFZAgent", lambda name: FakeAgent(name, lambda **kw: slow_agent("pfz", **kw)))
    monkeypatch.setattr("app.orchestration.orchestrator.WarningsAgent", lambda name: FakeAgent(name, lambda **kw: slow_agent("warnings", **kw)))
    monkeypatch.setattr("app.orchestration.orchestrator.SafetyEngine", FakeSafetyEngine)
    monkeypatch.setattr("app.orchestration.orchestrator.EvidenceValidator", FakeEvidenceValidator)
    monkeypatch.setattr("app.orchestration.orchestrator.ResponseSynthesizer", lambda name: FakeAgent(name, fake_synthesizer_run))

    orchestrator = Orchestrator(db=context.db, context=context, max_concurrency=2)
    intent = NormalizedIntent(query_type="fishing")
    result = await orchestrator.execute(intent)

    assert result.overall_status == "success"


@pytest.mark.asyncio
async def test_deterministic_final_result(monkeypatch):
    context = _make_context(user_message="Is it safe to fish?", query_type="fishing")

    async def fake_intent_run(**kwargs):
        return _intent_result(query_type="fishing")

    async def fake_weather_run(**kwargs):
        return _agent_data_result([{"variable": "wave_height", "value": 2.5, "unit": "m"}], "weather")

    async def fake_pfz_run(**kwargs):
        return _agent_data_result([{"score": 0.8}], "pfz")

    async def fake_warnings_run(**kwargs):
        return _agent_data_result([], "warnings")

    async def fake_synthesizer_run(**kwargs):
        return AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "test"}, evidence=[], errors=[]), attempts=1)

    monkeypatch.setattr("app.orchestration.orchestrator.IntentAgent", lambda name: FakeAgent(name, fake_intent_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WeatherAgent", lambda name: FakeAgent(name, fake_weather_run))
    monkeypatch.setattr("app.orchestration.orchestrator.PFZAgent", lambda name: FakeAgent(name, fake_pfz_run))
    monkeypatch.setattr("app.orchestration.orchestrator.WarningsAgent", lambda name: FakeAgent(name, fake_warnings_run))
    monkeypatch.setattr("app.orchestration.orchestrator.SafetyEngine", FakeSafetyEngine)
    monkeypatch.setattr("app.orchestration.orchestrator.EvidenceValidator", FakeEvidenceValidator)
    monkeypatch.setattr("app.orchestration.orchestrator.ResponseSynthesizer", lambda name: FakeAgent(name, fake_synthesizer_run))

    orchestrator = Orchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="fishing")
    result1 = await orchestrator.execute(intent)
    result2 = await orchestrator.execute(intent)

    assert result1.overall_status == result2.overall_status
    assert result1.safety_result == result2.safety_result


@pytest.mark.asyncio
async def test_llm_cannot_override_deterministic_safety_badge():
    context = _make_context(user_message="What are the warnings?", query_type="warnings")

    async def fake_intent_run(self, **kwargs):
        return _intent_result(query_type="warnings")

    async def fake_warnings_run(self, deps):
        return _agent_data_result([{"type": "cyclone", "severity": "extreme", "issued_by": "IMD"}], "warnings")

    class FakeSafetyEngineUnsafe:
        @staticmethod
        def evaluate(**kwargs):
            class FakeSafety:
                safety_badge = "UNSAFE"
                hazard_breakdown = None
                fishing_suitability = "POOR"
                is_indeterminate = False
                reasons = ["IMD extreme warning"]
            return FakeSafety()

    async def fake_synthesizer_run(self, deps):
        return AgentResult(status="success", result=AgentResultData(agent_name="synthesizer", status="success", data={"answer": "Unsafe", "safety_badge": "UNSAFE"}, evidence=[], errors=[]), attempts=1)

    class UnsafeOrchestrator(Orchestrator):
        async def _run_intent_agent(self):
            return await fake_intent_run(self)

        async def _run_warnings_agent(self, deps):
            return await fake_warnings_run(self, deps)

        def _run_safety_engine(self, deps):
            return AgentResult(status="success", result=FakeSafetyEngineUnsafe.evaluate(), attempts=1)

        def _run_evidence_validator(self, deps):
            return AgentResult(status="success", result=type("Validation", (), {"is_valid": True, "supported_claims": [], "unsupported_claims": [], "issues": [], "overall_confidence": 1.0})(), attempts=1)

        async def _run_response_synthesizer(self, deps):
            return await fake_synthesizer_run(self, deps)

    orchestrator = UnsafeOrchestrator(db=context.db, context=context)
    intent = NormalizedIntent(query_type="warnings")
    result = await orchestrator.execute(intent)

    assert result.safety_result["safety_badge"] == "UNSAFE"
    assert result.synthesis_result is not None
    assert result.synthesis_result["data"]["safety_badge"] == "UNSAFE"

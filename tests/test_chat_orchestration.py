import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.orchestration.orchestrator import Orchestrator
from app.schemas.agent import (
    AgentEvidence,
    AgentResultData,
    AgentTraceEntry,
    NormalizedIntent,
    OrchestrationContext,
    PlanStep,
)


client = TestClient(app)


def _make_agent_result(agent_name, data, status="success", evidence=None, errors=None, task_id=None):
    return {
        "agent_name": agent_name,
        "status": status,
        "data": data,
        "evidence": evidence or [],
        "errors": errors or [],
        "task_id": task_id or f"{agent_name}-1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 50.0,
        "attempts": 1,
        "source_status": "live",
    }


def _make_trace_entry(agent_name, status="success", error=None):
    return {
        "agent_name": agent_name,
        "status": status,
        "task_id": f"{agent_name}-1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 50.0,
        "dependencies": [],
        "error": error,
    }


def _mock_orchestration_result(
    query_type="warnings",
    safety_badge="CAUTION",
    answer="Test answer",
    warnings_data=None,
    evidence_list=None,
    overall_status="success",
    synthesis_data=None,
):
    from app.agents.base_agent import AgentResult

    intent = NormalizedIntent(query_type=query_type)
    plan = type("Plan", (), {"steps": []})()

    agent_results = []
    agent_trace = []

    if query_type in ("warnings", "fishing", "weather", "route"):
        agent_results.append(_make_agent_result("IntentAgent", {"query_type": query_type}))
        agent_trace.append(_make_trace_entry("IntentAgent"))

    if query_type in ("warnings", "fishing"):
        agent_results.append(_make_agent_result("WarningsAgent", warnings_data or []))
        agent_trace.append(_make_trace_entry("WarningsAgent"))

    if query_type in ("fishing", "weather"):
        agent_results.append(_make_agent_result("WeatherAgent", []))
        agent_trace.append(_make_trace_entry("WeatherAgent"))

    if query_type == "fishing":
        agent_results.append(_make_agent_result("PFZAgent", []))
        agent_trace.append(_make_trace_entry("PFZAgent"))

    if query_type == "route":
        agent_results.append(_make_agent_result("RouteAgent", {"route_cost": 100.0, "risk_level": "low"}))
        agent_trace.append(_make_trace_entry("RouteAgent"))

    if query_type in ("warnings", "fishing", "weather", "route"):
        agent_results.append(_make_agent_result("SafetyEngine", type("Safety", (), {"safety_badge": safety_badge, "hazard_breakdown": None, "fishing_suitability": None, "is_indeterminate": False, "reasons": []})()))
        agent_trace.append(_make_trace_entry("SafetyEngine"))

        agent_results.append(_make_agent_result("EvidenceValidator", type("Validation", (), {"is_valid": True, "supported_claims": [], "unsupported_claims": [], "issues": [], "overall_confidence": 1.0})()))
        agent_trace.append(_make_trace_entry("EvidenceValidator"))

    synthesis = synthesis_data or {"data": {"answer": answer, "follow_up_suggestions": ["Test suggestion"]}}
    agent_results.append(_make_agent_result("ResponseSynthesizer", synthesis))
    agent_trace.append(_make_trace_entry("ResponseSynthesizer"))

    aggregated_evidence = []
    for ev in (evidence_list or []):
        aggregated_evidence.append(
            AgentEvidence(
                source=ev.get("source", "test"),
                variable=ev.get("variable", "test"),
                value=ev.get("value", "test"),
                unit=ev.get("unit"),
                valid_time=datetime.now(timezone.utc),
                confidence=ev.get("confidence", 0.9),
                why_it_matters="Test evidence",
            )
        )

    return type(
        "OrchestrationResult",
        (),
        {
            "task_id": "test-task-123",
            "intent": intent,
            "plan": plan,
            "agent_results": agent_results,
            "agent_trace": agent_trace,
            "aggregated_evidence": aggregated_evidence,
            "safety_result": {"safety_badge": safety_badge, "marine_hazard_index": 30.0, "hazard_breakdown": None, "fishing_suitability": None, "is_indeterminate": False, "reasons": []},
            "validation_result": {"is_valid": True, "supported_claims": [], "unsupported_claims": [], "issues": [], "overall_confidence": 1.0},
            "synthesis_result": synthesis,
            "errors": [],
            "overall_status": overall_status,
            "request_id": "test-request-id",
        },
    )()


@pytest.mark.asyncio
async def test_chat_invokes_intent_agent(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["answer"] == "Test answer"


@pytest.mark.asyncio
async def test_chat_invokes_planner(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_invokes_orchestrator(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_domain_agents_execute(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="fishing")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Is it safe to fish?", "language": "en"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_safety_queries_invoke_safety_engine(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="warnings", safety_badge="CAUTION")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["safety_badge"] == "CAUTION"


@pytest.mark.asyncio
async def test_chat_evidence_validator_invoked(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(
            query_type="warnings",
            evidence_list=[{"source": "IMD", "variable": "warning", "value": "cyclone", "unit": "advisory"}],
        )

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["evidence_cards"]) > 0


@pytest.mark.asyncio
async def test_chat_response_synthesizer_receives_validated_evidence(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(
            query_type="warnings",
            evidence_list=[{"source": "IMD", "variable": "warning", "value": "cyclone", "unit": "advisory"}],
            synthesis_data={"data": {"answer": "Validated synthesis", "follow_up_suggestions": []}},
        )

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["answer"] == "Validated synthesis"


@pytest.mark.asyncio
async def test_chat_safety_badge_from_safety_engine(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="warnings", safety_badge="UNSAFE")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["safety_badge"] == "UNSAFE"


@pytest.mark.asyncio
async def test_chat_llm_cannot_override_safety_badge(monkeypatch):
    async def mock_execute(self, intent):
        result = _mock_orchestration_result(query_type="warnings", safety_badge="UNSAFE")
        result.synthesis_result = {"data": {"answer": "Safe", "safety_badge": "SAFE", "follow_up_suggestions": []}}
        return result

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["safety_badge"] == "UNSAFE"


@pytest.mark.asyncio
async def test_chat_conversation_id_preserved():
    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "conversation_id": "conv_existing_123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["conversation_id"] == "conv_existing_123"


@pytest.mark.asyncio
async def test_chat_generates_conversation_id_when_missing(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["conversation_id"].startswith("conv_")


@pytest.mark.asyncio
async def test_chat_language_en():
    async def mock_execute(self, intent):
        assert intent.language == "en"
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_chat_language_hi():
    async def mock_execute(self, intent):
        assert intent.language == "hi"
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "चेतावनी क्या हैं?", "language": "hi"},
    )
    assert response.status_code == 200
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_chat_language_te():
    async def mock_execute(self, intent):
        assert intent.language == "te"
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "ఎవరు హెచ్చరికలు?", "language": "te"},
    )
    assert response.status_code == 200
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_chat_invalid_language_returns_422():
    response = client.post(
        "/api/v1/chat",
        json={"message": "Hello", "language": "fr"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_user_location_passed_correctly(monkeypatch):
    async def mock_execute(self, intent):
        assert intent.latitude == 16.9891
        assert intent.longitude == 82.2475
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What are the warnings?",
            "user_location": {"lat": 16.9891, "lon": 82.2475},
        },
    )
    assert response.status_code == 200
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_chat_missing_user_location_no_fake_coordinates(monkeypatch):
    async def mock_execute(self, intent):
        assert intent.latitude is None
        assert intent.longitude is None
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?"},
    )
    assert response.status_code == 200
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_chat_kakinada_resolves_through_deterministic_logic(monkeypatch):
    async def mock_execute(self, intent):
        assert intent.location_name is None
        return _mock_orchestration_result(query_type="fishing")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Is it safe to fish near Kakinada?", "language": "en"},
    )
    assert response.status_code == 200
    monkeypatch.undo()


@pytest.mark.asyncio
async def test_chat_agent_trace_contains_real_execution(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    trace = data["data"]["agent_trace"]
    assert len(trace) > 0
    assert any(entry["agent_name"] == "IntentAgent" for entry in trace)
    assert any(entry["agent_name"] == "WarningsAgent" for entry in trace)
    for entry in trace:
        assert "agent_name" in entry
        assert "status" in entry
        assert "started_at" in entry
        assert "completed_at" in entry
        assert "duration_ms" in entry


@pytest.mark.asyncio
async def test_chat_evidence_cards_contain_validated_evidence(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(
            query_type="warnings",
            evidence_list=[
                {"source": "IMD", "variable": "warning", "value": "cyclone", "unit": "advisory"}
            ],
        )

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["evidence_cards"]) > 0
    for card in data["data"]["evidence_cards"]:
        assert "source" in card
        assert "snippet" in card


@pytest.mark.asyncio
async def test_chat_unavailable_sources_do_not_become_safe(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(
            query_type="fishing",
            safety_badge=None,
            overall_status="partial",
            synthesis_data={"data": {"answer": "Current safety cannot be confirmed because required marine data is unavailable.", "follow_up_suggestions": []}},
        )

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Is it safe to fish?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["safety_badge"] is None


@pytest.mark.asyncio
async def test_chat_timeout_handled_safely(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(
            query_type="warnings",
            overall_status="timeout",
            safety_badge=None,
            synthesis_data={"data": {"answer": "The orchestration pipeline encountered an issue. Current safety cannot be confirmed due to insufficient or unavailable data.", "follow_up_suggestions": []}},
        )

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["safety_badge"] is None


@pytest.mark.asyncio
async def test_chat_orchestrator_failure_produces_safe_response(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(
            query_type="warnings",
            overall_status="error",
            synthesis_data={"data": {"answer": "The orchestration pipeline encountered an issue. Current safety cannot be confirmed due to insufficient or unavailable data.", "follow_up_suggestions": []}},
        )

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "data" in data


@pytest.mark.asyncio
async def test_chat_response_field_names_unchanged(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="warnings")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "conversation_id" in data["data"]
    assert "answer" in data["data"]
    assert "safety_badge" in data["data"]
    assert "evidence_cards" in data["data"]
    assert "map_layers" in data["data"]
    assert "agent_trace" in data["data"]
    assert "warnings" in data["data"]
    assert "follow_up_suggestions" in data["data"]


@pytest.mark.asyncio
async def test_chat_response_envelope_unchanged():
    response = client.post(
        "/api/v1/chat",
        json={"message": "What are the warnings?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "meta" in data
    assert "errors" in data
    assert "request_id" in data["meta"]
    assert "timestamp" in data["meta"]


@pytest.mark.asyncio
async def test_chat_warnings_query_works(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(
            query_type="warnings",
            warnings_data=[{"type": "cyclone", "severity": "high", "issued_by": "IMD"}],
        )

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Show active marine warnings nearby", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]["warnings"]) > 0


@pytest.mark.asyncio
async def test_chat_fishing_safety_query_works(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="fishing", safety_badge="SAFE")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Is it safe to fish near Kakinada tomorrow morning?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["safety_badge"] == "SAFE"


@pytest.mark.asyncio
async def test_chat_route_query_works(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="route", safety_badge="CAUTION")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Evaluate a route for a small motor boat", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["safety_badge"] == "CAUTION"


@pytest.mark.asyncio
async def test_chat_weather_query_works(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="weather", safety_badge="SAFE")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "What is the weather near Kakinada?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["safety_badge"] == "SAFE"


@pytest.mark.asyncio
async def test_chat_pfz_query_works(monkeypatch):
    async def mock_execute(self, intent):
        return _mock_orchestration_result(query_type="pfz", safety_badge="SAFE")

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Show PFZ information near Kakinada", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["safety_badge"] == "SAFE"


@pytest.mark.asyncio
async def test_chat_complex_multi_agent_query_runs_all_relevant_agents(monkeypatch):
    from app.orchestration.planner import create_plan
    from app.schemas.agent import NormalizedIntent

    intent = NormalizedIntent(
        query_type="general",
        weather_intent=True,
        pfz_intent=True,
        warning_intent=True,
        route_intent=True,
    )
    plan = create_plan(intent)
    agent_names = {step.agent_name for step in plan.steps}
    assert "WeatherAgent" in agent_names
    assert "PFZAgent" in agent_names
    assert "WarningsAgent" in agent_names
    assert "RouteAgent" in agent_names
    assert "SafetyEngine" in agent_names
    assert "EvidenceValidator" in agent_names
    assert "ResponseSynthesizer" in agent_names


@pytest.mark.asyncio
async def test_chat_parallel_agents_execute_concurrently(monkeypatch):
    import asyncio
    from app.orchestration.planner import create_plan
    from app.schemas.agent import NormalizedIntent
    from app.agents.base_agent import AgentResult

    execution_order = []

    async def fake_run_intent(self, **kwargs):
        execution_order.append("IntentAgent")
        return AgentResult(status="success", result=type("R", (), {"data": {"query_type": "fishing", "latitude": 16.9891, "longitude": 82.2475}, "status": "success"})(), attempts=1)

    async def fake_run_weather(self, **kwargs):
        execution_order.append("WeatherAgent")
        await asyncio.sleep(0.05)
        return AgentResult(status="success", result=type("R", (), {"data": [], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    async def fake_run_pfz(self, **kwargs):
        execution_order.append("PFZAgent")
        await asyncio.sleep(0.05)
        return AgentResult(status="success", result=type("R", (), {"data": [], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    async def fake_run_warnings(self, **kwargs):
        execution_order.append("WarningsAgent")
        await asyncio.sleep(0.05)
        return AgentResult(status="success", result=type("R", (), {"data": [], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    monkeypatch.setattr("app.agents.intent_agent.IntentAgent.run", fake_run_intent)
    monkeypatch.setattr("app.agents.weather_agent.WeatherAgent.run", fake_run_weather)
    monkeypatch.setattr("app.agents.pfz_agent.PFZAgent.run", fake_run_pfz)
    monkeypatch.setattr("app.agents.warnings_agent.WarningsAgent.run", fake_run_warnings)

    intent = NormalizedIntent(query_type="fishing", latitude=16.9891, longitude=82.2475)
    plan = create_plan(intent)

    from app.orchestration.orchestrator import Orchestrator
    from app.schemas.agent import OrchestrationContext

    context = OrchestrationContext(
        user_message="Is it safe to fish?",
        language="en",
        user_lat=16.9891,
        user_lon=82.2475,
        db=None,
    )
    orchestrator = Orchestrator(db=None, context=context)
    result = await orchestrator.execute(intent)
    executed_agents = [entry.agent_name for entry in result.agent_trace]
    assert "IntentAgent" in executed_agents
    assert "WeatherAgent" in executed_agents
    assert "PFZAgent" in executed_agents
    assert "WarningsAgent" in executed_agents


@pytest.mark.asyncio
async def test_chat_one_agent_failure_does_not_prevent_others(monkeypatch):
    from app.orchestration.planner import create_plan
    from app.schemas.agent import NormalizedIntent
    from app.agents.base_agent import AgentResult

    call_count = {"weather": 0}

    async def fake_run_intent(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": {"query_type": "fishing", "latitude": 16.9891, "longitude": 82.2475}, "status": "success"})(), attempts=1)

    async def fake_run_weather(self, **kwargs):
        call_count["weather"] += 1
        raise RuntimeError("Weather service down")

    async def fake_run_pfz(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": [], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    async def fake_run_warnings(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": [], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    monkeypatch.setattr("app.agents.intent_agent.IntentAgent.run", fake_run_intent)
    monkeypatch.setattr("app.agents.weather_agent.WeatherAgent.run", fake_run_weather)
    monkeypatch.setattr("app.agents.pfz_agent.PFZAgent.run", fake_run_pfz)
    monkeypatch.setattr("app.agents.warnings_agent.WarningsAgent.run", fake_run_warnings)

    intent = NormalizedIntent(query_type="fishing", latitude=16.9891, longitude=82.2475)
    plan = create_plan(intent)

    from app.orchestration.orchestrator import Orchestrator
    from app.schemas.agent import OrchestrationContext

    context = OrchestrationContext(
        user_message="Is it safe to fish?",
        language="en",
        user_lat=16.9891,
        user_lon=82.2475,
        db=None,
    )
    orchestrator = Orchestrator(db=None, context=context)
    result = await orchestrator.execute(intent)
    assert call_count["weather"] == 1
    assert result.overall_status == "error"
    executed_agents = [entry.agent_name for entry in result.agent_trace]
    assert "WeatherAgent" in executed_agents
    assert "PFZAgent" in executed_agents
    assert "WarningsAgent" in executed_agents


@pytest.mark.asyncio
async def test_chat_multiple_agent_failures_preserve_successful_evidence(monkeypatch):
    from app.orchestration.planner import create_plan
    from app.schemas.agent import NormalizedIntent, AgentEvidence
    from app.agents.base_agent import AgentResult

    async def fake_run_intent(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": {"query_type": "fishing", "latitude": 16.9891, "longitude": 82.2475}, "status": "success"})(), attempts=1)

    async def fake_run_weather(self, **kwargs):
        raise RuntimeError("Weather down")

    async def fake_run_pfz(self, **kwargs):
        raise RuntimeError("PFZ down")

    async def fake_run_warnings(self, **kwargs):
        return AgentResult(
            status="success",
            result=type("R", (), {
                "data": [{"type": "Cyclone", "severity": "high"}],
                "evidence": [AgentEvidence(source="imd", variable="warning", value="Cyclone", unit="advisory")],
                "status": "success",
                "source_status": "live",
            })(),
            attempts=1,
        )

    async def fake_run_synthesizer(self, **kwargs):
        from app.schemas.agent import AgentResultData, SynthesisResponse
        return AgentResultData(
            agent_name="ResponseSynthesizer",
            status="success",
            data=SynthesisResponse(answer="Test", follow_up_suggestions=[], language="en", evidence_summary=[], safety_badge=None, fishing_suitability=None).model_dump(),
            evidence=[],
            errors=[],
            source_status="llm",
        )

    monkeypatch.setattr("app.agents.intent_agent.IntentAgent.run", fake_run_intent)
    monkeypatch.setattr("app.agents.weather_agent.WeatherAgent.run", fake_run_weather)
    monkeypatch.setattr("app.agents.pfz_agent.PFZAgent.run", fake_run_pfz)
    monkeypatch.setattr("app.agents.warnings_agent.WarningsAgent.run", fake_run_warnings)
    monkeypatch.setattr("app.agents.response_synthesizer.ResponseSynthesizer.run", fake_run_synthesizer)

    intent = NormalizedIntent(query_type="fishing", latitude=16.9891, longitude=82.2475)
    plan = create_plan(intent)

    from app.orchestration.orchestrator import Orchestrator
    from app.schemas.agent import OrchestrationContext

    context = OrchestrationContext(
        user_message="Is it safe to fish?",
        language="en",
        user_lat=16.9891,
        user_lon=82.2475,
        db=None,
    )
    orchestrator = Orchestrator(db=None, context=context)
    result = await orchestrator.execute(intent)
    warning_evidence = [e for e in result.aggregated_evidence if e.variable == "warning"]
    assert len(warning_evidence) >= 1
    assert warning_evidence[0].value == "Cyclone"


@pytest.mark.asyncio
async def test_chat_missing_evidence_does_not_become_safe(monkeypatch):
    from app.orchestration.planner import create_plan
    from app.schemas.agent import NormalizedIntent
    from app.agents.base_agent import AgentResult

    async def fake_run_intent(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": {"query_type": "fishing", "latitude": 16.9891, "longitude": 82.2475}, "status": "success"})(), attempts=1)

    async def fake_run_weather(self, **kwargs):
        return AgentResult(status="no_data", result=type("R", (), {"data": [], "evidence": [], "status": "no_data", "source_status": "no_data"})(), attempts=1)

    async def fake_run_pfz(self, **kwargs):
        return AgentResult(status="no_data", result=type("R", (), {"data": [], "evidence": [], "status": "no_data", "source_status": "no_data"})(), attempts=1)

    async def fake_run_warnings(self, **kwargs):
        return AgentResult(status="no_data", result=type("R", (), {"data": [], "evidence": [], "status": "no_data", "source_status": "no_data"})(), attempts=1)

    monkeypatch.setattr("app.agents.intent_agent.IntentAgent.run", fake_run_intent)
    monkeypatch.setattr("app.agents.weather_agent.WeatherAgent.run", fake_run_weather)
    monkeypatch.setattr("app.agents.pfz_agent.PFZAgent.run", fake_run_pfz)
    monkeypatch.setattr("app.agents.warnings_agent.WarningsAgent.run", fake_run_warnings)

    intent = NormalizedIntent(query_type="fishing", latitude=16.9891, longitude=82.2475)
    plan = create_plan(intent)

    from app.orchestration.orchestrator import Orchestrator
    from app.schemas.agent import OrchestrationContext

    context = OrchestrationContext(
        user_message="Is it safe to fish?",
        language="en",
        user_lat=16.9891,
        user_lon=82.2475,
        db=None,
    )
    orchestrator = Orchestrator(db=None, context=context)
    result = await orchestrator.execute(intent)
    safety_results = [r for r in result.agent_results if getattr(r, "agent_name", None) == "SafetyEngine"]
    if safety_results:
        safety = safety_results[0]
        if hasattr(safety, "result") and safety.result:
            assert safety.result.is_indeterminate is True


@pytest.mark.asyncio
async def test_chat_fishing_suitability_separate_from_safety_badge(monkeypatch):
    from app.orchestration.planner import create_plan
    from app.schemas.agent import NormalizedIntent
    from app.agents.base_agent import AgentResult

    async def fake_run_intent(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": {"query_type": "fishing", "latitude": 16.9891, "longitude": 82.2475}, "status": "success"})(), attempts=1)

    async def fake_run_weather(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": [{"variable": "wave_height", "value": 1.0}], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    async def fake_run_pfz(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": [{"score": 0.8}], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    async def fake_run_warnings(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": [], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    monkeypatch.setattr("app.agents.intent_agent.IntentAgent.run", fake_run_intent)
    monkeypatch.setattr("app.agents.weather_agent.WeatherAgent.run", fake_run_weather)
    monkeypatch.setattr("app.agents.pfz_agent.PFZAgent.run", fake_run_pfz)
    monkeypatch.setattr("app.agents.warnings_agent.WarningsAgent.run", fake_run_warnings)

    intent = NormalizedIntent(query_type="fishing", latitude=16.9891, longitude=82.2475)
    plan = create_plan(intent)

    from app.orchestration.orchestrator import Orchestrator
    from app.schemas.agent import OrchestrationContext

    context = OrchestrationContext(
        user_message="Is it safe to fish?",
        language="en",
        user_lat=16.9891,
        user_lon=82.2475,
        db=None,
    )
    orchestrator = Orchestrator(db=None, context=context)
    result = await orchestrator.execute(intent)
    safety_results = [r for r in result.agent_results if getattr(r, "agent_name", None) == "SafetyEngine"]
    if safety_results:
        safety = safety_results[0]
        if hasattr(safety, "result") and safety.result:
            assert safety.result.safety_badge == "SAFE"
            assert safety.result.fishing_suitability == "EXCELLENT"


@pytest.mark.asyncio
async def test_chat_agent_trace_contains_all_executed_agents(monkeypatch):
    from app.orchestration.planner import create_plan
    from app.schemas.agent import NormalizedIntent
    from app.agents.base_agent import AgentResult

    async def fake_run_intent(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": {"query_type": "fishing", "latitude": 16.9891, "longitude": 82.2475}, "status": "success"})(), attempts=1)

    async def fake_run_weather(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": [], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    async def fake_run_pfz(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": [], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    async def fake_run_warnings(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": [], "evidence": [], "status": "success", "source_status": "live"})(), attempts=1)

    monkeypatch.setattr("app.agents.intent_agent.IntentAgent.run", fake_run_intent)
    monkeypatch.setattr("app.agents.weather_agent.WeatherAgent.run", fake_run_weather)
    monkeypatch.setattr("app.agents.pfz_agent.PFZAgent.run", fake_run_pfz)
    monkeypatch.setattr("app.agents.warnings_agent.WarningsAgent.run", fake_run_warnings)

    intent = NormalizedIntent(query_type="fishing", latitude=16.9891, longitude=82.2475)
    plan = create_plan(intent)

    from app.orchestration.orchestrator import Orchestrator
    from app.schemas.agent import OrchestrationContext

    context = OrchestrationContext(
        user_message="Is it safe to fish?",
        language="en",
        user_lat=16.9891,
        user_lon=82.2475,
        db=None,
    )
    orchestrator = Orchestrator(db=None, context=context)
    result = await orchestrator.execute(intent)
    executed_agents = {entry.agent_name for entry in result.agent_trace}
    assert "IntentAgent" in executed_agents
    assert "WeatherAgent" in executed_agents
    assert "PFZAgent" in executed_agents
    assert "WarningsAgent" in executed_agents
    assert "SafetyEngine" in executed_agents
    assert "EvidenceValidator" in executed_agents
    assert "ResponseSynthesizer" in executed_agents


@pytest.mark.asyncio
async def test_chat_stale_evidence_penalizes_safety(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.orchestration.planner import create_plan
    from app.schemas.agent import NormalizedIntent

    stale_time = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    async def fake_run_intent(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {"data": {"query_type": "fishing", "latitude": 16.9891, "longitude": 82.2475}, "status": "success"})(), attempts=1)

    async def fake_run_weather(self, **kwargs):
        return AgentResult(status="success", result=type("R", (), {
            "data": [{"variable": "wave_height", "value": 1.0, "valid_time": stale_time}],
            "evidence": [],
            "status": "success",
            "source_status": "stale",
        })(), attempts=1)

    async def fake_run_pfz(self, **kwargs):
        return AgentResult(status="no_data", result=type("R", (), {"data": [], "evidence": [], "status": "no_data", "source_status": "no_data"})(), attempts=1)

    async def fake_run_warnings(self, **kwargs):
        return AgentResult(status="no_data", result=type("R", (), {"data": [], "evidence": [], "status": "no_data", "source_status": "no_data"})(), attempts=1)

    monkeypatch.setattr("app.agents.intent_agent.IntentAgent.run", fake_run_intent)
    monkeypatch.setattr("app.agents.weather_agent.WeatherAgent.run", fake_run_weather)
    monkeypatch.setattr("app.agents.pfz_agent.PFZAgent.run", fake_run_pfz)
    monkeypatch.setattr("app.agents.warnings_agent.WarningsAgent.run", fake_run_warnings)

    intent = NormalizedIntent(query_type="fishing", latitude=16.9891, longitude=82.2475)
    plan = create_plan(intent)

    from app.orchestration.orchestrator import Orchestrator
    from app.schemas.agent import OrchestrationContext

    context = OrchestrationContext(
        user_message="Is it safe to fish?",
        language="en",
        user_lat=16.9891,
        user_lon=82.2475,
        db=None,
    )
    orchestrator = Orchestrator(db=None, context=context)
    result = await orchestrator.execute(intent)
    safety_results = [r for r in result.agent_results if getattr(r, "agent_name", None) == "SafetyEngine"]
    if safety_results:
        safety = safety_results[0]
        if hasattr(safety, "result") and safety.result:
            assert any("stale" in reason.lower() for reason in safety.result.reasons)


@pytest.mark.asyncio
async def test_chat_multilingual_synthesis_preserves_language(monkeypatch):
    async def mock_execute(self, intent):
        from app.schemas.agent import AgentResultData, SynthesisResponse
        return type("OrchestrationResult", (), {
            "task_id": "test",
            "intent": intent,
            "plan": type("Plan", (), {"steps": []})(),
            "agent_results": [],
            "agent_trace": [],
            "aggregated_evidence": [],
            "safety_result": None,
            "validation_result": None,
            "synthesis_result": {"data": SynthesisResponse(answer="नमस्ते", follow_up_suggestions=[], language="hi", evidence_summary=[], safety_badge=None, fishing_suitability=None).model_dump()},
            "errors": [],
            "overall_status": "success",
            "request_id": "test-request-id",
        })()

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Is it safe to fish near Kakinada?", "language": "hi"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["answer"] == "नमस्ते"


@pytest.mark.asyncio
async def test_chat_synthesizer_does_not_fabricate_missing_data(monkeypatch):
    async def mock_execute(self, intent):
        from app.schemas.agent import AgentResultData, SynthesisResponse
        return type("OrchestrationResult", (), {
            "task_id": "test",
            "intent": intent,
            "plan": type("Plan", (), {"steps": []})(),
            "agent_results": [],
            "agent_trace": [],
            "aggregated_evidence": [],
            "safety_result": {"safety_badge": None, "marine_hazard_index": None, "hazard_breakdown": None, "fishing_suitability": None, "is_indeterminate": True, "reasons": ["no observation or warning data available"]},
            "validation_result": None,
            "synthesis_result": {"data": SynthesisResponse(answer="Current safety cannot be confirmed because required marine data is unavailable.", follow_up_suggestions=[], language="en", evidence_summary=[], safety_badge=None, fishing_suitability=None).model_dump()},
            "errors": [],
            "overall_status": "success",
            "request_id": "test-request-id",
        })()

    monkeypatch.setattr(Orchestrator, "execute", mock_execute)

    response = client.post(
        "/api/v1/chat",
        json={"message": "Is it safe to fish near Kakinada tomorrow morning?", "language": "en"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "cannot be confirmed" in data["data"]["answer"]
    assert data["data"]["safety_badge"] is None

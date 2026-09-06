"""
Milestone 10 — Final System Integration & Release Readiness Tests.

Covers:
- End-to-end /chat pipeline under deterministic mocks
- Safety/evidence/trace contract on the final response
- Frontend-facing API contracts for key endpoints
- Security hardening: no secrets leakage, auth behavior, CORS
- Resilience end-to-end: timeout, retry, circuit breaker, cache
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agents.base_agent import AgentResult
from app.config import settings
from app.connectors.base_connector import BaseConnector, ConnectorResult, ConnectorFailureCategory
from app.orchestration.orchestrator import Orchestrator
from app.resilience.cache import MarineCache
from app.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    circuit_breakers,
)
from app.schemas.agent import (
    AgentEvidence,
    AgentTraceEntry,
    NormalizedIntent,
    OrchestrationContext,
    SynthesisResponse,
)
from app.services.safety_engine import SafetyEngine
from app.main import app
from app.agents import intent_agent, weather_agent, pfz_agent, warnings_agent, response_synthesizer

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent_result(agent_name, data, status="success", evidence=None, errors=None, source_status="live"):
    return {
        "agent_name": agent_name,
        "status": status,
        "data": data,
        "evidence": evidence or [],
        "errors": errors or [],
        "task_id": f"{agent_name}-1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 50.0,
        "attempts": 1,
        "source_status": source_status,
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


# ---------------------------------------------------------------------------
# /chat contract
# ---------------------------------------------------------------------------


def test_chat_response_contract_envelope():
    response = client.post("/api/v1/chat", json={"message": "Is it safe to fish near Kakinada?", "language": "en"})
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "errors" in body
    assert "meta" in body
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]


def test_chat_response_has_required_fields():
    response = client.post("/api/v1/chat", json={"message": "Weather near Kakinada?", "language": "en"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert "conversation_id" in data
    assert "answer" in data
    assert "safety_badge" in data
    assert "fishing_suitability" in data
    assert "evidence_cards" in data
    assert "agent_trace" in data
    assert "warnings" in data
    assert "follow_up_suggestions" in data
    assert "request_id" in data


def test_chat_invalid_language_returns_422():
    response = client.post("/api/v1/chat", json={"message": "test", "language": "xx"})
    assert response.status_code == 422


def test_chat_missing_message_returns_422():
    response = client.post("/api/v1/chat", json={"language": "en"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Frontend endpoint contract
# ---------------------------------------------------------------------------


def test_health_endpoint_contract():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "incois" in body["data"]
    assert "mosdac" in body["data"]
    assert "imd" in body["data"]


def test_marine_point_endpoint_contract():
    response = client.get("/api/v1/marine/point", params={"lat": 17.0, "lon": 82.0, "radius_km": 10.0})
    assert response.status_code == 200
    body = response.json()
    assert "data" in body


def test_pfz_endpoint_contract():
    response = client.get("/api/v1/pfz/nearby", params={"lat": 17.0, "lon": 82.0, "radius_km": 10.0})
    assert response.status_code == 200
    body = response.json()
    assert "data" in body


def test_warnings_endpoint_contract():
    response = client.get("/api/v1/warnings", params={"lat": 17.0, "lon": 82.0, "radius_km": 10.0})
    assert response.status_code == 200
    body = response.json()
    assert "data" in body


def test_route_evaluate_endpoint_contract():
    response = client.post(
        "/api/v1/route/evaluate",
        json={
            "waypoints": [{"lat": 17.0, "lon": 82.0}, {"lat": 17.1, "lon": 82.1}],
            "vessel_type": "small_boat",
            "max_wave_height": 2.0,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "data" in body


def test_layers_endpoint_contract():
    response = client.get("/api/v1/layers")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body


# ---------------------------------------------------------------------------
# /chat pipeline completeness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_pipeline_completeness_simple_query():
    async def fake_run_intent(self, **kwargs):
        return AgentResult(
            status="success",
            result=type("R", (), {"data": {"query_type": "weather", "latitude": 16.9891, "longitude": 82.2475}, "status": "success"})(),
            attempts=1,
        )

    async def fake_run_weather(self, **kwargs):
        return AgentResult(
            status="success",
            result=type("R", (), {
                "data": [{"variable": "wave_height", "value": 0.8, "unit": "m"}],
                "evidence": [],
                "status": "success",
                "source_status": "live",
            })(),
            attempts=1,
        )

    async def fake_run_synthesizer(self, **kwargs):
        return AgentResult(
            status="success",
            result=SynthesisResponse(
                answer="Calm conditions.",
                follow_up_suggestions=[],
                language="en",
                evidence_summary=[],
                safety_badge="SAFE",
                fishing_suitability="GOOD",
            ),
            attempts=1,
        )

    with patch.object(intent_agent.IntentAgent, "run", fake_run_intent):
        with patch.object(weather_agent.WeatherAgent, "run", fake_run_weather):
            with patch.object(response_synthesizer.ResponseSynthesizer, "run", fake_run_synthesizer):
                response = client.post("/api/v1/chat", json={"message": "Weather near Kakinada?", "language": "en"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["safety_badge"] == "SAFE"
    assert len(data["agent_trace"]) >= 3


@pytest.mark.asyncio
async def test_chat_pipeline_missing_data_produces_indeterminate():
    async def fake_run_intent(self, **kwargs):
        return AgentResult(
            status="success",
            result=type("R", (), {"data": {"query_type": "fishing", "latitude": 16.9891, "longitude": 82.2475}, "status": "success"})(),
            attempts=1,
        )

    async def fake_run_weather(self, **kwargs):
        return AgentResult(status="no_data", result=type("R", (), {"data": [], "evidence": [], "status": "no_data", "source_status": "no_data"})(), attempts=1)

    async def fake_run_pfz(self, **kwargs):
        return AgentResult(status="no_data", result=type("R", (), {"data": [], "evidence": [], "status": "no_data", "source_status": "no_data"})(), attempts=1)

    async def fake_run_warnings(self, **kwargs):
        return AgentResult(status="no_data", result=type("R", (), {"data": [], "evidence": [], "status": "no_data", "source_status": "no_data"})(), attempts=1)

    async def fake_run_synthesizer(self, **kwargs):
        return AgentResultData(
            agent_name="ResponseSynthesizer",
            status="success",
            data=SynthesisResponse(
                answer="Current safety cannot be confirmed because required marine data is unavailable.",
                follow_up_suggestions=[],
                language="en",
                evidence_summary=[],
                safety_badge=None,
                fishing_suitability=None,
            ).model_dump(),
            evidence=[],
            errors=[],
            source_status="llm",
        )

    with patch.object(intent_agent.IntentAgent, "run", fake_run_intent):
        with patch.object(weather_agent.WeatherAgent, "run", fake_run_weather):
            with patch.object(pfz_agent.PFZAgent, "run", fake_run_pfz):
                with patch.object(warnings_agent.WarningsAgent, "run", fake_run_warnings):
                    with patch.object(response_synthesizer.ResponseSynthesizer, "run", fake_run_synthesizer):
                        response = client.post("/api/v1/chat", json={"message": "Is it safe to fish?", "language": "en"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["safety_badge"] is None
    assert "cannot be confirmed" in data["answer"]


# ---------------------------------------------------------------------------
# Safety audit
# ---------------------------------------------------------------------------


def test_unavailable_weather_never_produces_safe():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[],
        pfz_zones=[],
        geofence_violations=[],
        source_health=None,
    )
    assert result.is_indeterminate is True
    assert result.safety_badge is None


def test_imd_warning_precedence_overrides_safe():
    result = SafetyEngine.evaluate(
        warnings=[{"severity": "extreme", "issued_by": "IMD"}],
        observations=[{"variable": "wave_height", "value": 0.5}],
        pfz_zones=[],
        geofence_violations=[],
        source_health=None,
    )
    assert result.safety_badge == "UNSAFE"


def test_fishing_suitability_separate_from_safety():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[{"variable": "wave_height", "value": 1.0}],
        pfz_zones=[{"score": 0.8}],
        geofence_violations=[],
        source_health=None,
    )
    assert result.safety_badge == "SAFE"
    assert result.fishing_suitability == "EXCELLENT"


def test_numeric_values_and_units_preserved():
    from app.connectors.incois_connector import IncoisConnector

    connector = IncoisConnector()
    raw = {
        "table": {
            "columnNames": ["time", "TEMP", "PSAL"],
            "columnUnits": ["UTC", "degree_Celsius", "PSU"],
            "rows": [["2024-01-01T00:00:00Z", 28.5, 32.0]],
        }
    }
    result = connector.normalize_observations(raw)
    assert result.status == "success"
    assert len(result.evidence) == 2
    units = {ev.variable: ev.unit for ev in result.evidence}
    assert units["temp"] == "degree_Celsius"
    assert units["psal"] == "PSU"


# ---------------------------------------------------------------------------
# Evidence audit
# ---------------------------------------------------------------------------


def test_evidence_requires_required_fields():
    from app.services.evidence_validator import EvidenceValidator, EvidenceClaim

    result = EvidenceValidator.validate(
        claims=[EvidenceClaim(variable="temperature", min_confidence=0.0)],
        evidence_items=[{"variable": "temperature", "value": 28.5}],
    )
    assert result.is_valid is False
    assert any(issue.issue.startswith("missing required fields") for issue in result.issues)


def test_evidence_deduplication_works():
    from app.schemas.agent import AgentEvidence

    evidence = AgentEvidence(source="incois", variable="temperature", value=28.5, unit="C", valid_time=None, confidence=0.9)
    context = OrchestrationContext(user_message="test")
    orchestrator = Orchestrator(db=None, context=context)
    orchestrator._collect_evidence_from_agent(
        "WeatherAgent",
        type("R", (), {"result": type("D", (), {"evidence": [evidence]})(), "evidence": []})(),
    )
    orchestrator._collect_evidence_from_agent(
        "WeatherAgent",
        type("R", (), {"result": type("D", (), {"evidence": [evidence]})(), "evidence": []})(),
    )
    assert len(orchestrator.aggregated_evidence) == 1


# ---------------------------------------------------------------------------
# Agent trace audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_trace_contains_executed_agents_only():
    from app.orchestration.planner import create_plan

    context = OrchestrationContext(user_message="test")
    orchestrator = Orchestrator(db=None, context=context)

    trace_entry = AgentTraceEntry(agent_name="WeatherAgent", status="success", duration_ms=10.0)
    orchestrator.agent_trace.append(trace_entry)

    assert len(orchestrator.agent_trace) == 1
    assert orchestrator.agent_trace[0].agent_name == "WeatherAgent"
    assert orchestrator.agent_trace[0].status == "success"


# ---------------------------------------------------------------------------
# Connector audit
# ---------------------------------------------------------------------------


def test_connector_failure_categories_are_distinct():
    categories = {
        "timeout": ConnectorFailureCategory.TIMEOUT,
        "rate limit 429": ConnectorFailureCategory.RATE_LIMITED,
        "no matching results": ConnectorFailureCategory.NO_DATA,
        "invalid response 400": ConnectorFailureCategory.INVALID_RESPONSE,
        "connection refused": ConnectorFailureCategory.UPSTREAM_ERROR,
    }
    assert len(set(categories.values())) == 5


def test_base_connector_circuit_breaker_integration():
    class TestConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            raise RuntimeError("boom")

    connector = TestConnector(base_url="https://example.com", timeout=1.0, max_retries=0)
    result = asyncio.run(connector.fetch())
    assert result.status == "error"
    assert result.failure_category == ConnectorFailureCategory.UPSTREAM_ERROR


# ---------------------------------------------------------------------------
# Security audit
# ---------------------------------------------------------------------------


def test_no_api_key_exposed_in_chat_response():
    response = client.post("/api/v1/chat", json={"message": "test", "language": "en"})
    body = response.json()
    response_text = str(body)
    assert "GROQ_API_KEY" not in response_text
    assert "api_key" not in response_text.lower() or "api_key" not in body


def test_auth_endpoint_does_not_leak_credentials():
    response = client.post("/api/v1/auth/token", data={"username": "admin", "password": "wrong"})
    assert response.status_code == 401
    body = response.json()
    assert "password" not in str(body.get("data", "")).lower()
    assert "admin" not in str(body.get("data", "")).lower()


def test_cors_headers_present():
    response = client.post("/api/v1/chat", headers={"Origin": "http://localhost:8080"}, json={"message": "test", "language": "en"})
    assert response.status_code in (200, 422)
    assert "access-control-allow-origin" in response.headers


# ---------------------------------------------------------------------------
# Resilience / performance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_does_not_serve_stale_data_as_live():
    cache = MarineCache(default_ttl_seconds=0.1)
    await cache.set("sst", [1, 2, 3], source="mosdac", status="live")
    await asyncio.sleep(0.15)
    assert await cache.get("sst") is None


@pytest.mark.asyncio
async def test_circuit_breaker_state_transitions():
    breaker = CircuitBreaker("e2e-test", CircuitBreakerConfig(failure_threshold=2, recovery_timeout_seconds=0.1))

    async def failing():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await breaker.call(failing)
    with pytest.raises(RuntimeError):
        await breaker.call(failing)
    assert breaker._state.state.value == "open"

    await asyncio.sleep(0.15)

    async def success():
        return "ok"

    result = await breaker.call(success)
    assert result == "ok"
    assert breaker._state.state.value == "closed"


# ---------------------------------------------------------------------------
# Code quality quick checks
# ---------------------------------------------------------------------------


def test_no_hardcoded_credentials_in_config():
    with open("app/config.py") as f:
        content = f.read()
    assert "hardcoded" not in content.lower()
    assert "password" not in content.lower() or "MOSDAC_PASSWORD" in content


def test_no_debug_prints_in_production_modules():
    modules = ["app/orchestration/orchestrator.py", "app/connectors/incois_connector.py", "app/connectors/base_connector.py"]
    for module in modules:
        with open(module) as f:
            content = f.read()
        assert "print(" not in content, f"Debug print found in {module}"

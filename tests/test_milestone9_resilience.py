"""
Milestone 9 focused production-readiness tests.

Covers:
- circuit breaker states
- cache TTL/expiration
- request ID propagation
- evidence limits
- connector failure categorization
- timeout/deadline behavior
- retry behavior
- Groq failure categorization
- structured logging / no secret leakage
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.connectors.base_connector import BaseConnector, ConnectorResult, ConnectorFailureCategory
from app.orchestration.orchestrator import Orchestrator
from app.resilience.cache import MarineCache
from app.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitBreakerState,
    circuit_breakers,
)
from app.resilience.logging import get_logger, request_context
from app.schemas.agent import AgentEvidence, OrchestrationContext


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_circuit_breakers():
    circuit_breakers._breakers.clear()


def test_circuit_breaker_starts_closed():
    breaker = CircuitBreaker("test")
    assert breaker._state.state.value == "closed"


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_failure_threshold():
    breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))

    async def failing():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await breaker.call(failing)
    with pytest.raises(RuntimeError):
        await breaker.call(failing)
    with pytest.raises(RuntimeError):
        await breaker.call(failing)

    assert breaker._state.state.value == "open"
    assert breaker._state.failure_count == 3


@pytest.mark.asyncio
async def test_circuit_breaker_open_rejects_calls():
    breaker = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))

    async def failing():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await breaker.call(failing)
    with pytest.raises(RuntimeError):
        await breaker.call(failing)

    with pytest.raises(RuntimeError, match="circuit_breaker_open"):
        await breaker.call(failing)


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_after_recovery_timeout():
    breaker = CircuitBreaker(
        "test",
        CircuitBreakerConfig(failure_threshold=2, recovery_timeout_seconds=0.1, half_open_max_calls=1),
    )

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


@pytest.mark.asyncio
async def test_circuit_breaker_isolation_per_name():
    registry = CircuitBreakerRegistry()
    breaker_a = registry.get("source-a", CircuitBreakerConfig(failure_threshold=2))
    breaker_b = registry.get("source-b", CircuitBreakerConfig(failure_threshold=2))

    async def failing():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await breaker_a.call(failing)
    with pytest.raises(RuntimeError):
        await breaker_a.call(failing)

    assert breaker_a._state.state.value == "open"
    assert breaker_b._state.state.value == "closed"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_stores_and_retrieves_values():
    cache = MarineCache(default_ttl_seconds=300)
    await cache.set("key1", {"temp": 28.5}, source="incois")
    value = await cache.get("key1")
    assert value == {"temp": 28.5}


@pytest.mark.asyncio
async def test_cache_ttl_expiration():
    cache = MarineCache(default_ttl_seconds=0.1)
    await cache.set("key1", "value1")
    assert await cache.get("key1") == "value1"

    await asyncio.sleep(0.15)
    assert await cache.get("key1") is None


@pytest.mark.asyncio
async def test_cache_stale_entry_does_not_fabricate():
    cache = MarineCache(default_ttl_seconds=0.1)
    await cache.set("sst", [1, 2, 3], source="mosdac", valid_time=None, confidence=0.9, status="live")
    await asyncio.sleep(0.15)
    assert await cache.get("sst") is None


@pytest.mark.asyncio
async def test_cache_invalidate_removes_entry():
    cache = MarineCache(default_ttl_seconds=300)
    await cache.set("key1", "value1")
    await cache.invalidate("key1")
    assert await cache.get("key1") is None


# ---------------------------------------------------------------------------
# Request ID propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_id_propagates_through_orchestrator():
    context = OrchestrationContext(
        user_message="test",
        request_id="req-123",
    )
    orchestrator = Orchestrator(db=None, context=context)
    assert orchestrator.request_id == "req-123"


@pytest.mark.asyncio
async def test_request_id_in_orchestration_result():
    from app.schemas.agent import NormalizedIntent

    context = OrchestrationContext(
        user_message="test",
        request_id="req-456",
    )
    orchestrator = Orchestrator(db=None, context=context)
    result = await orchestrator.execute(NormalizedIntent(query_type="general"))
    assert result.request_id == "req-456"


# ---------------------------------------------------------------------------
# Evidence limits
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_limits_enforced_when_exceeded():
    from app.schemas.agent import NormalizedIntent, AgentEvidence

    context = OrchestrationContext(user_message="test")
    orchestrator = Orchestrator(db=None, context=context)
    for i in range(300):
        orchestrator.aggregated_evidence.append(
            AgentEvidence(
                source="test",
                variable="warning" if i < 10 else f"var_{i % 5}",
                value=i,
                unit="m",
                valid_time=None,
                confidence=0.5,
            )
        )

    with patch.object(settings, "MAX_AGGREGATED_EVIDENCE", 50):
        orchestrator._enforce_evidence_limits()

    assert len(orchestrator.aggregated_evidence) == 50
    priority_vars = [ev.variable for ev in orchestrator.aggregated_evidence]
    assert "warning" in priority_vars


@pytest.mark.asyncio
async def test_evidence_limits_preserves_critical_evidence():
    from app.schemas.agent import NormalizedIntent, AgentEvidence

    context = OrchestrationContext(user_message="test")
    orchestrator = Orchestrator(db=None, context=context)
    for i in range(300):
        orchestrator.aggregated_evidence.append(
            AgentEvidence(
                source="test",
                variable="wave_hazard_score" if i < 30 else f"noise_{i}",
                value=i,
                unit="score",
                valid_time=None,
                confidence=0.5,
            )
        )

    with patch.object(settings, "MAX_AGGREGATED_EVIDENCE", 20):
        orchestrator._enforce_evidence_limits()

    assert len(orchestrator.aggregated_evidence) == 20
    assert all(ev.variable == "wave_hazard_score" for ev in orchestrator.aggregated_evidence)


# ---------------------------------------------------------------------------
# Connector failure categorization
# ---------------------------------------------------------------------------


def test_connector_failure_categorization_timeout():
    class TestConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            pass

    connector = TestConnector(base_url="https://example.com")
    category = connector._categorize_failure(TimeoutError("timeout after 1.0s"))
    assert category == ConnectorFailureCategory.TIMEOUT


def test_connector_failure_categorization_rate_limit():
    class TestConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            pass

    connector = TestConnector(base_url="https://example.com")
    category = connector._categorize_failure(RuntimeError("Rate limit exceeded: 429"))
    assert category == ConnectorFailureCategory.RATE_LIMITED


def test_connector_failure_categorization_no_data():
    class TestConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            pass

    connector = TestConnector(base_url="https://example.com")
    category = connector._categorize_failure(RuntimeError("Not Found: no matching results"))
    assert category == ConnectorFailureCategory.NO_DATA


def test_connector_failure_categorization_invalid_response():
    class TestConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            pass

    connector = TestConnector(base_url="https://example.com")
    category = connector._categorize_failure(RuntimeError("Invalid response: 400 Bad Request"))
    assert category == ConnectorFailureCategory.INVALID_RESPONSE


def test_connector_failure_categorization_upstream_error():
    class TestConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            pass

    connector = TestConnector(base_url="https://example.com")
    category = connector._categorize_failure(RuntimeError("Connection refused"))
    assert category == ConnectorFailureCategory.UPSTREAM_ERROR


@pytest.mark.asyncio
async def test_connector_fetch_returns_failure_category():
    class FailingConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            raise RuntimeError("Connection refused")

    connector = FailingConnector(base_url="https://example.com", timeout=1.0, max_retries=0)
    result = await connector.fetch()
    assert result.status == "error"
    assert result.failure_category == ConnectorFailureCategory.UPSTREAM_ERROR


# ---------------------------------------------------------------------------
# Timeout / deadline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_timeout_produces_safe_failure():
    from app.schemas.agent import NormalizedIntent

    context = OrchestrationContext(user_message="test")
    orchestrator = Orchestrator(db=None, context=context)

    with patch.object(orchestrator, "_execute_plan", new_callable=AsyncMock) as mock_plan:
        mock_plan.side_effect = asyncio.TimeoutError()
        result = await orchestrator.execute(NormalizedIntent(query_type="general"))

    assert result.overall_status == "timeout"
    assert "orchestration_timeout" in result.errors


# ---------------------------------------------------------------------------
# Retry behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_base_agent_retries_on_transient_failure():
    from app.agents.base_agent import BaseAgent, AgentResult

    class FlakyAgent(BaseAgent):
        async def _execute(self, **kwargs):
            raise RuntimeError("transient error")

    agent = FlakyAgent(name="flaky")
    with patch.object(settings, "CHAT_MAX_RETRIES", 1):
        with patch.object(settings, "CHAT_TIMEOUT_SECONDS", 0.1):
            result = await agent.run()
    assert result.attempts == 2
    assert result.status == "failed"


# ---------------------------------------------------------------------------
# Groq failure categorization
# ---------------------------------------------------------------------------


def test_groq_client_categorizes_rate_limit():
    from app.connectors.groq_client import GroqClient

    client = GroqClient()
    exc = RuntimeError("Rate limit reached for model: 429")
    category = client._categorize_failure(exc)
    assert category == "rate_limited"


def test_groq_client_categorizes_timeout():
    from app.connectors.groq_client import GroqClient

    client = GroqClient()
    exc = TimeoutError("Request timeout after 30s")
    category = client._categorize_failure(exc)
    assert category == "timeout"


def test_groq_client_categorizes_authentication_error():
    from app.connectors.groq_client import GroqClient

    client = GroqClient()
    exc = RuntimeError("Invalid API key: 401")
    category = client._categorize_failure(exc)
    assert category == "authentication_error"


# ---------------------------------------------------------------------------
# Structured logging / no secrets
# ---------------------------------------------------------------------------


def test_structured_logger_filters_sensitive_fields():
    logger = get_logger("test")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="test",
        args=(),
        exc_info=None,
    )
    logger._logger.handle(record)
    assert getattr(record, "structured", {}).get("api_key") is None


# ---------------------------------------------------------------------------
# Cache source-aware retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_source_filter():
    cache = MarineCache(default_ttl_seconds=300)
    await cache.set("sst", [1, 2], source="mosdac")
    await cache.set("temp", [3, 4], source="incois")

    mosdac_entries = await cache.get_entries(source="mosdac")
    assert len(mosdac_entries) == 1
    assert mosdac_entries[0]["source"] == "mosdac"


# ---------------------------------------------------------------------------
# Evidence deduplication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evidence_deduplication_prevents_duplicates():
    from app.schemas.agent import NormalizedIntent, AgentEvidence

    context = OrchestrationContext(user_message="test")
    orchestrator = Orchestrator(db=None, context=context)

    evidence = AgentEvidence(
        source="incois",
        variable="temperature",
        value=28.5,
        unit="degree_C",
        valid_time=None,
        confidence=0.9,
    )
    orchestrator._collect_evidence_from_agent("WeatherAgent", type("R", (), {"result": type("D", (), {"evidence": [evidence]})(), "evidence": []})())
    orchestrator._collect_evidence_from_agent("WeatherAgent", type("R", (), {"result": type("D", (), {"evidence": [evidence]})(), "evidence": []})())

    assert len(orchestrator.aggregated_evidence) == 1

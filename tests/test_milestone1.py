import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.agents.base_agent import BaseAgent, AgentResult
from app.config import settings
from app.connectors.groq_client import GroqClient, groq_client
from app.models.evidence_item import EvidenceItem
from app.repositories.evidence_repository import (
    add_evidence_item,
    batch_add_evidence_items,
    delete_evidence_for_task,
    get_evidence_by_source,
    get_evidence_by_task_id,
)
from app.services.warnings_service import get_active_warnings_within_radius


class FakeAgent(BaseAgent):
    async def _execute(self, db=None):
        return {"ok": True}


class FailingAgent(BaseAgent):
    async def _execute(self, db=None):
        raise RuntimeError("transient failure")


class TimeoutAgent(BaseAgent):
    async def _execute(self, db=None):
        await asyncio.sleep(10)
        return {"ok": True}


def test_settings_loads_groq_defaults():
    assert hasattr(settings, "GROQ_API_KEY")
    assert hasattr(settings, "GROQ_MODEL")
    assert hasattr(settings, "CHAT_TIMEOUT_SECONDS")
    assert hasattr(settings, "CHAT_MAX_RETRIES")
    assert hasattr(settings, "CACHE_STALE_THRESHOLD_SECONDS")
    assert settings.GROQ_MODEL == "llama-3.3-70b-versatile"
    assert settings.CHAT_TIMEOUT_SECONDS == 8.0
    assert settings.CHAT_MAX_RETRIES == 2
    assert settings.CACHE_STALE_THRESHOLD_SECONDS == 3600


def test_groq_client_raises_without_api_key(monkeypatch):
    monkeypatch.setattr("app.connectors.groq_client.settings.GROQ_API_KEY", "")
    client = GroqClient()
    with pytest.raises(RuntimeError, match="GROQ_API_KEY is not configured"):
        client._ensure_client()


def test_groq_client_chat_raises_without_api_key(monkeypatch):
    monkeypatch.setattr("app.connectors.groq_client.settings.GROQ_API_KEY", "")
    client = GroqClient()
    with pytest.raises(RuntimeError, match="GROQ_API_KEY is not configured"):
        asyncio.run(client.chat(messages=[{"role": "user", "content": "hi"}]))


def test_groq_client_does_not_expose_api_key_in_logs(monkeypatch, caplog):
    monkeypatch.setattr("app.connectors.groq_client.settings.GROQ_API_KEY", "secret-key-123")
    client = GroqClient()
    client._ensure_client()
    asyncio.run(client.close())
    for record in caplog.records:
        assert "secret-key-123" not in record.getMessage()


@pytest.mark.asyncio
async def test_base_agent_succeeds_on_first_attempt(monkeypatch):
    agent = FakeAgent(name="test")
    result = await agent.run()
    assert result.status == "success"
    assert result.result == {"ok": True}
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_base_agent_retries_on_failure(monkeypatch):
    call_count = 0

    class RetryAgent(BaseAgent):
        async def _execute(self, db=None):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("transient")
            return {"ok": True}

    agent = RetryAgent(name="retry-test")
    monkeypatch.setattr("app.agents.base_agent.settings.CHAT_MAX_RETRIES", 2)
    monkeypatch.setattr("app.agents.base_agent.settings.CHAT_TIMEOUT_SECONDS", 1.0)
    result = await agent.run()
    assert result.status == "success"
    assert result.attempts == 3


@pytest.mark.asyncio
async def test_base_agent_fails_after_max_retries(monkeypatch):
    agent = FailingAgent(name="fail-test")
    monkeypatch.setattr("app.agents.base_agent.settings.CHAT_MAX_RETRIES", 1)
    monkeypatch.setattr("app.agents.base_agent.settings.CHAT_TIMEOUT_SECONDS", 0.5)
    result = await agent.run()
    assert result.status == "failed"
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_base_agent_times_out(monkeypatch):
    agent = TimeoutAgent(name="timeout-test")
    monkeypatch.setattr("app.agents.base_agent.settings.CHAT_MAX_RETRIES", 0)
    monkeypatch.setattr("app.agents.base_agent.settings.CHAT_TIMEOUT_SECONDS", 0.1)
    result = await agent.run()
    assert result.status == "timeout"
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_base_agent_records_timing():
    agent = FakeAgent(name="timing-test")
    result = await agent.run()
    assert result.duration_ms >= 0
    assert result.started_at <= result.ended_at


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: __import__("app.db.base", fromlist=["Base"]).Base.metadata.create_all(sync_conn))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_evidence_repository_add_and_get_by_task_id(db_session: AsyncSession):
    task_id = uuid.uuid4()
    item = EvidenceItem(
        task_id=task_id,
        source="incois",
        variable="sst",
        value="28.5",
        unit="celsius",
        valid_time=datetime.now(timezone.utc),
        confidence=0.95,
    )
    created = await add_evidence_item(db_session, item)
    assert created.id is not None

    results = await get_evidence_by_task_id(db_session, task_id)
    assert len(results) == 1
    assert results[0].source == "incois"
    assert results[0].variable == "sst"
    assert results[0].value == "28.5"


@pytest.mark.asyncio
async def test_evidence_repository_batch_add(db_session: AsyncSession):
    task_id = uuid.uuid4()
    items = [
        EvidenceItem(
            task_id=task_id,
            source="imd",
            variable="wave_height",
            value="2.5",
            unit="m",
            valid_time=datetime.now(timezone.utc),
            confidence=0.8,
        ),
        EvidenceItem(
            task_id=task_id,
            source="incois",
            variable="wind_speed",
            value="15.0",
            unit="kt",
            valid_time=datetime.now(timezone.utc),
            confidence=0.9,
        ),
    ]
    created = await batch_add_evidence_items(db_session, items)
    assert len(created) == 2
    assert all(item.id is not None for item in created)

    results = await get_evidence_by_task_id(db_session, task_id)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_evidence_repository_get_by_source(db_session: AsyncSession):
    task_id = uuid.uuid4()
    item = EvidenceItem(
        task_id=task_id,
        source="mosdac",
        variable="chlorophyll",
        value="0.2",
        unit="mg/m3",
        valid_time=datetime.now(timezone.utc),
        confidence=0.85,
    )
    await add_evidence_item(db_session, item)

    results = await get_evidence_by_source(db_session, "mosdac")
    assert len(results) == 1
    assert results[0].variable == "chlorophyll"


@pytest.mark.asyncio
async def test_evidence_repository_delete_for_task(db_session: AsyncSession):
    task_id = uuid.uuid4()
    item = EvidenceItem(
        task_id=task_id,
        source="incois",
        variable="sst",
        value="28.5",
        unit="celsius",
        valid_time=datetime.now(timezone.utc),
        confidence=0.95,
    )
    await add_evidence_item(db_session, item)

    results = await get_evidence_by_task_id(db_session, task_id)
    assert len(results) == 1

    await delete_evidence_for_task(db_session, task_id)
    results = await get_evidence_by_task_id(db_session, task_id)
    assert len(results) == 0


@pytest.mark.asyncio
async def test_get_active_warnings_within_radius(monkeypatch):
    fake_rows = [
        (
            type("Warning", (), {
                "id": uuid.uuid4(),
                "type": "cyclone",
                "severity": "high",
                "geometry": None,
                "issued_by": "IMD",
                "valid_from": datetime.now(timezone.utc),
                "valid_to": datetime.now(timezone.utc),
            })(),
            '{"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]}',
        )
    ]

    async def fake_repo_get(db, lat, lon, radius_km):
        assert lat == 16.9
        assert lon == 82.2
        assert radius_km == 50.0
        return fake_rows

    monkeypatch.setattr(
        "app.services.warnings_service.warnings_repository.get_active_warnings_within_radius",
        fake_repo_get,
    )

    db = AsyncMock()
    results = await get_active_warnings_within_radius(16.9, 82.2, 50.0, db)
    assert len(results) == 1
    assert results[0].type == "cyclone"
    assert results[0].severity.value == "high"

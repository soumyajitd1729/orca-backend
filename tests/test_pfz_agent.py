from unittest.mock import AsyncMock, patch

import pytest

from app.agents.pfz_agent import PFZAgent
from app.resilience.cache import marine_cache
from app.schemas.agent import AgentResultData


@pytest.fixture(autouse=True)
async def _clear_pfz_cache():
    await marine_cache.clear()
    yield
    await marine_cache.clear()


class FakePFZZone:
    def __init__(self, score, components, valid_time):
        self.id = "pfz-1"
        self.geometry = None
        self.score = score
        self.components = components
        self.valid_time = valid_time

    def model_dump(self):
        return {
            "id": self.id,
            "geometry": self.geometry,
            "score": self.score,
            "components": self.components,
            "valid_time": self.valid_time.isoformat() if self.valid_time else None,
        }


@pytest.mark.asyncio
async def test_pfz_agent_success(monkeypatch):
    from datetime import datetime, timezone
    fake_zones = [
        FakePFZZone(0.85, {"sst": 28.5}, datetime.now(timezone.utc)),
    ]

    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        return fake_zones

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)
    assert isinstance(result.result, AgentResultData)
    assert result.result.status == "success"
    assert len(result.result.data) == 1
    assert len(result.result.evidence) == 1
    assert result.result.source_status == "live"
    assert result.result.duration_ms is not None and result.result.duration_ms >= 0


@pytest.mark.asyncio
async def test_pfz_agent_no_data(monkeypatch):
    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        return []

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)
    assert result.result.status == "no_data"
    assert result.result.data == []
    assert result.result.evidence == []


@pytest.mark.asyncio
async def test_pfz_agent_unavailable(monkeypatch):
    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        raise RuntimeError("DB down")

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)
    assert result.result.status == "unavailable"
    assert result.result.data is None
    assert len(result.result.errors) > 0


@pytest.mark.asyncio
async def test_pfz_agent_evidence_generation(monkeypatch):
    from datetime import datetime, timezone
    fake_zones = [
        FakePFZZone(0.9, {"sst": 28.0}, datetime.now(timezone.utc)),
    ]

    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        return fake_zones

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)
    assert len(result.result.evidence) == 1
    assert result.result.evidence[0].source == "incois"
    assert result.result.evidence[0].variable == "pfz_score"
    assert result.result.evidence[0].value == 0.9
    assert result.result.evidence[0].unit == "index"
    assert "why_it_matters" in result.result.evidence[0].model_dump()


@pytest.mark.asyncio
async def test_pfz_agent_uses_cache_when_db_empty(monkeypatch):
    from datetime import datetime, timezone

    cache_key = "incois:pfz:16.90:82.20:25.0"
    zone_dict = {
        "id": "pfz-1",
        "score": 0.85,
        "components": {"sst": 28.5},
        "valid_time": datetime.now(timezone.utc).isoformat(),
    }
    await marine_cache.set(cache_key, [zone_dict], source="incois", status="cached", ttl_seconds=86400)

    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        return []

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)

    assert result.result.status == "success"
    assert len(result.result.data) == 1
    assert result.result.source_status == "cached"
    assert result.result.data[0]["score"] == 0.85


@pytest.mark.asyncio
async def test_pfz_agent_uses_stale_cache_when_db_empty(monkeypatch):
    from datetime import datetime, timezone, timedelta
    from app.resilience.cache import CacheEntry

    cache_key = "incois:pfz:16.90:82.20:25.0"
    zone_dict = {
        "id": "pfz-1",
        "score": 0.85,
        "components": {"sst": 28.5},
        "valid_time": datetime.now(timezone.utc).isoformat(),
    }
    old_entry = CacheEntry(
        key=cache_key,
        value=[zone_dict],
        created_at=datetime.now(timezone.utc) - timedelta(seconds=7200),
        source="incois",
        status="cached",
    )
    marine_cache._store[cache_key] = old_entry

    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        return []

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)

    assert result.result.status == "success"
    assert len(result.result.data) == 1
    assert result.result.source_status == "stale"
    assert "pfz_data_stale" in result.result.errors
    assert result.result.data[0]["score"] == 0.85

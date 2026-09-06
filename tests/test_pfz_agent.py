from unittest.mock import AsyncMock, patch

import pytest

from app.agents.pfz_agent import PFZAgent
from app.schemas.agent import AgentResultData


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

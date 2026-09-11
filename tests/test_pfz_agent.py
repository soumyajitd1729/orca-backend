from datetime import date, datetime, timezone, timedelta
from unittest.mock import AsyncMock

import pytest

from app.agents.pfz_agent import PFZAgent
from app.resilience.cache import CacheEntry, marine_cache
from app.schemas.agent import AgentResultData


@pytest.fixture(autouse=True)
async def _clear_pfz_cache():
    await marine_cache.clear()
    yield
    await marine_cache.clear()


class FakePFZZone:
    def __init__(
        self,
        score=None,
        components=None,
        valid_time=None,
        source_type="incois_pfz_advisory",
        source_name="INCOIS PFZ Advisory",
        sector=None,
        landing_center=None,
        depth=None,
        distance_km=None,
        direction=None,
        forecast_date=None,
        valid_until=None,
    ):
        self.id = "pfz-1"
        self.geometry = None
        self.score = score
        self.components = components or {}
        self.valid_time = valid_time or datetime.now(timezone.utc)
        self.source_type = source_type
        self.source_name = source_name
        self.sector = sector
        self.landing_center = landing_center
        self.depth = depth
        self.distance_km = distance_km
        self.direction = direction
        self.forecast_date = forecast_date
        self.valid_until = valid_until

    def model_dump(self):
        return {
            "id": self.id,
            "geometry": self.geometry,
            "score": self.score,
            "components": self.components,
            "valid_time": self.valid_time.isoformat() if self.valid_time else None,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "sector": self.sector,
            "landing_center": self.landing_center,
            "depth": self.depth,
            "distance_km": self.distance_km,
            "direction": self.direction,
            "forecast_date": self.forecast_date.isoformat() if self.forecast_date else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
        }


@pytest.mark.asyncio
async def test_pfz_agent_success(monkeypatch):
    fake_zones = [
        FakePFZZone(
            score=None,
            components={"source_type": "incois_pfz_advisory"},
            valid_time=datetime.now(timezone.utc),
            sector="SOUTH ANDHRA PRADESH",
            landing_center="Machilipatnam",
            depth="50-80m",
            distance_km=15.0,
            direction="SW",
            forecast_date=date.today(),
        ),
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
    fake_zones = [
        FakePFZZone(
            score=None,
            components={"source_type": "incois_pfz_advisory"},
            valid_time=datetime.now(timezone.utc),
            sector="SOUTH ANDHRA PRADESH",
            landing_center="Machilipatnam",
            depth="50-80m",
            distance_km=15.0,
            direction="SW",
            forecast_date=date.today(),
        ),
    ]

    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        return fake_zones

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)
    assert len(result.result.evidence) == 1
    assert result.result.evidence[0].source == "INCOIS PFZ Advisory"
    assert result.result.evidence[0].variable == "pfz_advisory"
    assert result.result.evidence[0].value == "SOUTH ANDHRA PRADESH"
    assert result.result.evidence[0].unit == "advisory"
    assert result.result.evidence[0].confidence is None
    assert "why_it_matters" in result.result.evidence[0].model_dump()
    assert result.result.evidence[0].url_ref == "https://incois.gov.in/MarineFisheries/PfzAdvisory"


@pytest.mark.asyncio
async def test_pfz_agent_no_fabricated_score(monkeypatch):
    fake_zones = [
        FakePFZZone(
            score=None,
            components={"source_type": "incois_pfz_advisory"},
            valid_time=datetime.now(timezone.utc),
            sector="SOUTH ANDHRA PRADESH",
            landing_center="Machilipatnam",
        ),
    ]

    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        return fake_zones

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)
    assert result.result.status == "success"
    assert result.result.evidence[0].confidence is None
    assert result.result.data[0]["score"] is None


@pytest.mark.asyncio
async def test_pfz_agent_uses_cache_when_db_empty(monkeypatch):
    cache_key = "incois:pfz:16.90:82.20:25.0"
    zone_dict = {
        "id": "pfz-1",
        "score": None,
        "components": {"source_type": "incois_pfz_advisory"},
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "source_type": "incois_pfz_advisory",
        "source_name": "INCOIS PFZ Advisory",
        "sector": "SOUTH ANDHRA PRADESH",
        "landing_center": "Machilipatnam",
        "depth": "50-80m",
        "distance_km": 15.0,
        "direction": "SW",
        "forecast_date": date.today().isoformat(),
        "valid_until": date.today().isoformat(),
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
    assert result.result.data[0]["score"] is None
    assert result.result.data[0]["source_type"] == "incois_pfz_advisory"


@pytest.mark.asyncio
async def test_pfz_agent_uses_stale_cache_when_db_empty(monkeypatch):
    cache_key = "incois:pfz:16.90:82.20:25.0"
    zone_dict = {
        "id": "pfz-1",
        "score": None,
        "components": {"source_type": "incois_pfz_advisory"},
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "source_type": "incois_pfz_advisory",
        "source_name": "INCOIS PFZ Advisory",
        "sector": "SOUTH ANDHRA PRADESH",
        "landing_center": "Machilipatnam",
        "depth": "50-80m",
        "distance_km": 15.0,
        "direction": "SW",
        "forecast_date": date.today().isoformat(),
        "valid_until": date.today().isoformat(),
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
    assert result.result.data[0]["score"] is None
    assert result.result.data[0]["source_type"] == "incois_pfz_advisory"


@pytest.mark.asyncio
async def test_pfz_agent_expired_advisory_is_stale(monkeypatch):
    from datetime import datetime, timezone, timedelta
    from app.resilience.cache import CacheEntry

    cache_key = "incois:pfz:16.90:82.20:25.0"
    zone_dict = {
        "id": "pfz-1",
        "score": None,
        "components": {"source_type": "incois_pfz_advisory"},
        "valid_time": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        "source_type": "incois_pfz_advisory",
        "source_name": "INCOIS PFZ Advisory",
        "sector": "SOUTH ANDHRA PRADESH",
        "landing_center": "Machilipatnam",
        "depth": "50-80m",
        "distance_km": 15.0,
        "direction": "SW",
        "forecast_date": (date.today() - timedelta(days=2)).isoformat(),
        "valid_until": (date.today() - timedelta(days=1)).isoformat(),
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
    assert result.result.source_status == "stale"
    assert "pfz_data_stale" in result.result.errors


@pytest.mark.asyncio
async def test_pfz_agent_demo_source_status(monkeypatch):
    fake_zones = [
        FakePFZZone(
            score=0.529,
            components={
                "observation_id": "PFZ100002",
                "sst_c": 28.36,
                "chlorophyll_mg_m3": 1.668,
                "pfz_probability": 0.529,
                "pfz": 1,
                "pfz_class": "Medium",
                "source_type": "DEMO_SIMULATED",
            },
            valid_time=datetime.now(timezone.utc),
            source_type="DEMO_SIMULATED",
            source_name="ORCA Hackathon Synthetic PFZ Dataset",
            depth="62.8m",
            distance_km=22.39,
            forecast_date=date.today(),
        ),
    ]

    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        return fake_zones

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)
    assert result.result.status == "success"
    assert result.result.source_status == "demo"
    assert len(result.result.evidence) == 1
    assert result.result.evidence[0].source == "ORCA Hackathon Synthetic PFZ Dataset"
    assert "DEMO PFZ DATA" in result.result.evidence[0].why_it_matters
    assert "SYNTHETIC" in result.result.evidence[0].why_it_matters
    assert result.result.evidence[0].value == "Demo PFZ (Medium)"


@pytest.mark.asyncio
async def test_pfz_agent_demo_no_fabricated_official_score(monkeypatch):
    fake_zones = [
        FakePFZZone(
            score=0.529,
            components={
                "observation_id": "PFZ100002",
                "pfz_probability": 0.529,
                "pfz_class": "Medium",
                "source_type": "DEMO_SIMULATED",
            },
            valid_time=datetime.now(timezone.utc),
            source_type="DEMO_SIMULATED",
            source_name="ORCA Hackathon Synthetic PFZ Dataset",
        ),
    ]

    async def fake_get_pfz_zones(db, lat, lon, radius_km):
        return fake_zones

    monkeypatch.setattr("app.agents.pfz_agent.pfz_service.get_pfz_zones", fake_get_pfz_zones)

    agent = PFZAgent(name="pfz")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=25.0)
    assert result.result.status == "success"
    assert result.result.data[0]["components"]["pfz_probability"] == 0.529
    assert "pfz_class" in result.result.data[0]["components"]
    assert result.result.data[0]["source_type"] == "DEMO_SIMULATED"

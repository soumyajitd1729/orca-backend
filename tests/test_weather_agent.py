from unittest.mock import AsyncMock, patch

import pytest

from app.agents.weather_agent import WeatherAgent
from app.connectors.imd_connector import ImdConnector
from app.resilience.cache import marine_cache
from app.schemas.agent import AgentResultData
from datetime import datetime, timezone, timedelta


@pytest.fixture(autouse=True)
async def _clear_weather_cache():
    await marine_cache.clear()
    yield
    await marine_cache.clear()


class FakeObservation:
    def __init__(self, variable, value, unit, confidence=0.9, observed_at=None, source_time=None):
        self.id = "obs-1"
        self.variable = variable
        self.value = value
        self.unit = unit
        self.geometry = None
        self.observed_at = observed_at
        self.source_time = source_time if source_time else observed_at
        self.source_id = None
        self.quality_flag = "good"
        self.confidence = confidence

    def model_dump(self):
        return {
            "id": self.id,
            "variable": self.variable,
            "value": self.value,
            "unit": self.unit,
            "geometry": self.geometry,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "source_time": self.source_time.isoformat() if self.source_time else None,
            "source_id": self.source_id,
            "quality_flag": self.quality_flag,
            "confidence": self.confidence,
        }


@pytest.mark.asyncio
async def test_weather_agent_success(monkeypatch):
    fake_obs = [
        FakeObservation("sst", 28.5, "celsius"),
        FakeObservation("wind_speed", 15.0, "kt"),
    ]

    async def fake_get_observations(db, **kwargs):
        return fake_obs

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)
    assert isinstance(result.result, AgentResultData)
    assert result.result.status == "success"
    assert len(result.result.data) == 2
    assert len(result.result.evidence) == 2
    assert result.result.source_status == "live"
    assert result.result.duration_ms is not None and result.result.duration_ms >= 0


@pytest.mark.asyncio
async def test_weather_agent_no_data(monkeypatch):
    async def fake_get_observations(db, **kwargs):
        return []

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)
    assert result.result.status == "no_data"
    assert result.result.data == []
    assert result.result.evidence == []


@pytest.mark.asyncio
async def test_weather_agent_unavailable(monkeypatch):
    async def fake_get_observations(db, **kwargs):
        raise RuntimeError("DB down")

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)
    assert result.result.status == "unavailable"
    assert result.result.data is None
    assert len(result.result.errors) > 0


@pytest.mark.asyncio
async def test_weather_agent_evidence_generation(monkeypatch):
    fake_obs = [
        FakeObservation("wave_height", 2.5, "m", confidence=0.85),
    ]

    async def fake_get_observations(db, **kwargs):
        return fake_obs

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)
    assert len(result.result.evidence) == 1
    assert result.result.evidence[0].source == "incois"
    assert result.result.evidence[0].variable == "wave_height"
    assert result.result.evidence[0].value == 2.5
    assert result.result.evidence[0].unit == "m"
    assert result.result.evidence[0].confidence == 0.85
    assert "why_it_matters" in result.result.evidence[0].model_dump()


@pytest.mark.asyncio
async def test_weather_agent_uses_cache_when_incois_fails(monkeypatch):
    from datetime import datetime, timezone
    from app.resilience.cache import CacheEntry

    cache_key = "incois:weather:16.90:82.20:10.0"
    obs_dict = {
        "variable": "temperature",
        "value": 28.5,
        "unit": "celsius",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.9,
        "source": "incois",
    }
    await marine_cache.set(
        cache_key,
        [obs_dict],
        source="incois",
        status="cached",
        ttl_seconds=86400,
    )

    async def fake_get_observations(db, **kwargs):
        return []

    async def fake_search_datasets(*args, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["search_failed"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", fake_search_datasets)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)

    assert result.result.status == "success"
    assert len(result.result.evidence) == 1
    assert result.result.source_status == "cached"
    assert result.result.evidence[0].value == 28.5


@pytest.mark.asyncio
async def test_weather_agent_uses_stale_cache_when_incois_fails(monkeypatch):
    from datetime import datetime, timezone, timedelta

    cache_key = "incois:weather:16.90:82.20:10.0"
    obs_dict = {
        "variable": "temperature",
        "value": 28.5,
        "unit": "celsius",
        "valid_time": datetime.now(timezone.utc).isoformat(),
        "confidence": 0.9,
        "source": "incois",
    }
    from app.resilience.cache import CacheEntry
    old_entry = CacheEntry(
        key=cache_key,
        value=[obs_dict],
        created_at=datetime.now(timezone.utc) - timedelta(seconds=7200),
        source="incois",
        status="cached",
    )
    marine_cache._store[cache_key] = old_entry

    async def fake_get_observations(db, **kwargs):
        return []

    async def fake_search_datasets(*args, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["search_failed"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", fake_search_datasets)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)

    assert result.result.status == "success"
    assert len(result.result.evidence) == 1
    assert result.result.source_status == "stale"
    assert "incois_weather_data_stale" in result.result.errors
    assert result.result.evidence[0].value == 28.5


@pytest.mark.asyncio
async def test_weather_agent_uses_prototype_fallback_when_incois_unavailable(monkeypatch):
    monkeypatch.setattr("app.config.settings.PROTOTYPE_WEATHER_API_URL", "https://api.example.com/weather")

    async def fake_get_observations(db, **kwargs):
        return []

    async def fake_search_datasets(*args, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["search_failed"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    async def fake_fetch(self, **kwargs):
        from app.connectors.base_connector import ConnectorEvidence, ConnectorResult
        return ConnectorResult(
            status="success",
            data={"temperature": 29.1, "wind_speed": 12.0},
            evidence=[
                ConnectorEvidence(
                    source="prototype_weather",
                    variable="air_temperature",
                    value=29.1,
                    unit="celsius",
                    valid_time=datetime.utcnow(),
                    confidence=0.5,
                    why_it_matters="Air temperature affects crew comfort and equipment performance.",
                    url_ref="https://api.example.com/weather",
                ),
                ConnectorEvidence(
                    source="prototype_weather",
                    variable="wind_speed",
                    value=12.0,
                    unit="kt",
                    valid_time=datetime.utcnow(),
                    confidence=0.5,
                    why_it_matters="Wind speed affects sea state and vessel handling.",
                    url_ref="https://api.example.com/weather",
                ),
            ],
            source_status="prototype",
            retrieved_at=datetime.utcnow(),
        )

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", fake_search_datasets)
    monkeypatch.setattr("app.connectors.prototype_weather_connector.PrototypeWeatherConnector.fetch", fake_fetch)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)

    assert result.result.status == "success"
    assert len(result.result.evidence) == 2
    assert result.result.source_status == "prototype"
    assert "weather_data_from_prototype_fallback" in result.result.errors
    variables = {ev.variable for ev in result.result.evidence}
    assert "air_temperature" in variables
    assert "wind_speed" in variables
    for ev in result.result.evidence:
        assert ev.source == "prototype_weather"
        assert ev.confidence == 0.5


@pytest.mark.asyncio
async def test_weather_agent_prototype_fallback_unavailable_returns_no_data(monkeypatch):
    monkeypatch.setattr("app.config.settings.PROTOTYPE_WEATHER_API_URL", "https://api.example.com/weather")

    async def fake_get_observations(db, **kwargs):
        return []

    async def fake_search_datasets(*args, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["search_failed"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    async def fake_fetch(self, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["prototype_api_down"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", fake_search_datasets)
    monkeypatch.setattr("app.connectors.prototype_weather_connector.PrototypeWeatherConnector.fetch", fake_fetch)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)

    assert result.result.status == "no_data"
    assert result.result.evidence == []


@pytest.mark.asyncio
async def test_weather_agent_no_prototype_when_not_configured(monkeypatch):
    monkeypatch.setattr("app.config.settings.PROTOTYPE_WEATHER_API_URL", "")

    async def fake_get_observations(db, **kwargs):
        return []

    async def fake_search_datasets(*args, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["search_failed"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", fake_search_datasets)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)

    assert result.result.status == "no_data"
    assert result.result.evidence == []


@pytest.mark.asyncio
async def test_weather_agent_prototype_does_not_present_as_incois(monkeypatch):
    monkeypatch.setattr("app.config.settings.PROTOTYPE_WEATHER_API_URL", "https://api.example.com/weather")

    async def fake_get_observations(db, **kwargs):
        return []

    async def fake_search_datasets(*args, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["search_failed"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    async def fake_fetch(self, **kwargs):
        from app.connectors.base_connector import ConnectorEvidence, ConnectorResult
        return ConnectorResult(
            status="success",
            data={"temperature": 29.1},
            evidence=[
                ConnectorEvidence(
                    source="prototype_weather",
                    variable="air_temperature",
                    value=29.1,
                    unit="celsius",
                    valid_time=datetime.utcnow(),
                    confidence=0.5,
                    why_it_matters="Air temperature affects crew comfort and equipment performance.",
                    url_ref="https://api.example.com/weather",
                ),
            ],
            source_status="prototype",
            retrieved_at=datetime.utcnow(),
        )

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", fake_search_datasets)
    monkeypatch.setattr("app.connectors.prototype_weather_connector.PrototypeWeatherConnector.fetch", fake_fetch)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)

    assert result.result.status == "success"
    assert result.result.source_status == "prototype"
    for ev in result.result.evidence:
        assert ev.source == "prototype_weather"
        assert ev.source != "incois"


@pytest.mark.asyncio
async def test_weather_agent_passes_time_expression_to_imd_connector(monkeypatch):
    async def fake_get_observations(db, **kwargs):
        return []

    async def fake_search_datasets(*args, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["search_failed"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    captured: dict[str, Any] = {}

    async def fake_get_current_weather(self, lat=None, lon=None, time_expression=None):
        captured["time_expression"] = time_expression
        from app.connectors.base_connector import ConnectorResult, ConnectorEvidence
        return ConnectorResult(
            status="success",
            evidence=[
                ConnectorEvidence(
                    source="open_meteo",
                    variable="temperature",
                    value=26.4,
                    unit="celsius",
                    valid_time=datetime.utcnow(),
                    confidence=0.5,
                    url_ref="https://api.open-meteo.com/v1/forecast",
                ),
            ],
            source_status="live",
            retrieved_at=datetime.utcnow(),
        )

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", fake_search_datasets)

    with patch.object(ImdConnector, "get_current_weather", fake_get_current_weather):
        agent = WeatherAgent(name="weather")
        db = AsyncMock()
        result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0, time_expression="tomorrow_morning")

    assert captured["time_expression"] == "tomorrow_morning"
    assert result.result.status == "success"
    assert result.result.source_status == "live"
    assert result.result.evidence[0].source == "open_meteo"


@pytest.mark.asyncio
async def test_weather_agent_open_meteo_failure_does_not_invent_data(monkeypatch):
    async def fake_get_observations(db, **kwargs):
        return []

    async def fake_search_datasets(*args, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["search_failed"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    async def fake_get_current_weather(self, lat=None, lon=None, time_expression=None):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="error",
            errors=["open_meteo_down"],
            source_status="unavailable",
            retrieved_at=datetime.utcnow(),
        )

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", fake_search_datasets)
    monkeypatch.setattr("app.connectors.imd_connector.ImdConnector.get_current_weather", fake_get_current_weather)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)

    assert result.result.status == "no_data"
    assert result.result.evidence == []

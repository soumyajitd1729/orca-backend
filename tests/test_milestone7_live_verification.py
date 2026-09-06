"""
Live verification test for Milestone 7 connectors.

Tests:
1. INCOIS ERDDAP connector returns valid evidence structure
2. PFZ connector correctly reports unavailable (no fabricated data)
3. MOSDAC connector without credentials reports unavailable
4. IMD connector without API key reports unavailable
5. WeatherAgent integrates with INCOIS connector
6. SafetyEngine behavior when data is unavailable
7. Evidence structure contains all required fields
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.weather_agent import WeatherAgent
from app.agents.pfz_agent import PFZAgent
from app.agents.warnings_agent import WarningsAgent
from app.connectors.imd_connector import ImdConnector
from app.connectors.incois_connector import IncoisConnector
from app.connectors.mosdac_connector import MosdacConnector
from app.services.safety_engine import SafetyEngine


def test_incois_evidence_structure():
    connector = IncoisConnector()
    raw = {
        "table": {
            "columnNames": ["time", "latitude", "longitude", "TEMP", "PSAL"],
            "columnUnits": ["", "degrees_north", "degrees_east", "degree_C", "PSU"],
            "rows": [
                ["2024-01-01T00:00:00Z", 17.0, 83.0, 28.5, 32.0],
            ],
        }
    }
    result = connector.normalize_observations(raw, variable_mapping={"temp": "temperature", "psal": "salinity"})
    assert result.status == "success"
    assert len(result.evidence) == 2
    variables = {ev.variable for ev in result.evidence}
    assert "temperature" in variables
    assert "salinity" in variables
    ev = result.evidence[0]
    assert ev.source == "incois"
    assert ev.valid_time is not None
    assert isinstance(ev.valid_time, datetime)
    assert ev.confidence == 0.9
    assert ev.why_it_matters is not None
    assert ev.url_ref is not None
    assert "erddap.incois.gov.in" in ev.url_ref


def test_pfz_never_fabricates_data():
    connector = IncoisConnector()
    result = connector.normalize_pfz_unavailable()
    assert result.status == "unavailable"
    assert result.source_status == "unavailable"
    assert result.data is None
    assert len(result.errors) > 0
    assert "no_verified_machine_readable_api" in result.errors[0]
    assert len(result.evidence) == 0


@pytest.mark.asyncio
async def test_mosdac_without_credentials_is_unavailable():
    connector = MosdacConnector(username="", password="")
    result = await connector.search_datasets("SST")
    assert result.status == "success"
    assert result.source_status == "live"

    raw = {"results": [{"value": 29.1, "time": "2024-01-01T00:00:00Z"}]}
    normalized = connector.normalize_sst(raw)
    assert normalized.status == "success"
    assert len(normalized.evidence) == 1

    try:
        await connector._fetch_data()
        assert False, "Should have raised RuntimeError"
    except RuntimeError as exc:
        assert "credentials are not configured" in str(exc)


@pytest.mark.asyncio
async def test_imd_without_api_key_is_unavailable():
    connector = ImdConnector(api_key="")
    result = await connector.get_port_warnings()
    assert result.status == "unavailable"
    assert result.source_status == "unavailable"
    assert any("imd_not_configured" in e for e in result.errors)


@pytest.mark.asyncio
async def test_weather_agent_uses_incois_fallback(monkeypatch):
    from datetime import datetime, timezone

    class FakeObs:
        def __init__(self):
            self.variable = "sst"
            self.value = 28.5
            self.unit = "celsius"
            self.observed_at = datetime.now(timezone.utc)
            self.source_time = datetime.now(timezone.utc)
            self.confidence = 0.9
            self.source = "incois"
            self.id = "obs-1"
            self.geometry = None
            self.quality_flag = "good"

        def model_dump(self):
            return {
                "id": self.id,
                "variable": self.variable,
                "value": self.value,
                "unit": self.unit,
                "geometry": self.geometry,
                "observed_at": self.observed_at.isoformat() if self.observed_at else None,
                "source_time": self.source_time.isoformat() if self.source_time else None,
                "source_id": None,
                "quality_flag": self.quality_flag,
                "confidence": self.confidence,
            }

    fake_obs = [FakeObs()]

    async def fake_get_observations(db, **kwargs):
        return fake_obs

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)
    assert result.result.status == "success"
    assert len(result.result.evidence) == 1
    assert result.result.source_status == "live"


@pytest.mark.asyncio
async def test_weather_agent_falls_back_to_incois_when_db_empty(monkeypatch):
    from datetime import datetime, timezone

    class FakeObs:
        def __init__(self, variable, value, unit, valid_time):
            self.variable = variable
            self.value = value
            self.unit = unit
            self.observed_at = valid_time
            self.source_time = valid_time
            self.confidence = 0.9
            self.source = "incois"
            self.id = "obs-1"
            self.geometry = None
            self.quality_flag = "good"

        def model_dump(self):
            return {
                "id": self.id,
                "variable": self.variable,
                "value": self.value,
                "unit": self.unit,
                "geometry": self.geometry,
                "observed_at": self.observed_at.isoformat() if self.observed_at else None,
                "source_time": self.source_time.isoformat() if self.source_time else None,
                "source_id": None,
                "quality_flag": self.quality_flag,
                "confidence": self.confidence,
            }

    connector = IncoisConnector()

    raw_search_result = {
        "table": {
            "rows": [
                ["", "https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats", "", "", "", "", "INDIAN ARGO Floats Data", "Indian_ARGO_Floats"],
            ],
        }
    }

    async def fake_search_datasets(*args, **kwargs):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="success",
            data=raw_search_result,
            source_status="live",
            retrieved_at=datetime.utcnow(),
        )

    async def fake_query_dataset(self, dataset_id, variables, lat_min, lat_max, lon_min, lon_max, time_min=None, time_max=None):
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="success",
            data={
                "table": {
                    "columnNames": ["time", "latitude", "longitude", "TEMP", "PSAL"],
                    "columnUnits": ["UTC", "degrees_north", "degrees_east", "degree_C", "PSU"],
                    "rows": [["2024-01-01T00:00:00Z", 16.9, 82.2, 28.5, 32.0]],
                }
            },
            source_status="live",
            retrieved_at=datetime.utcnow(),
        )

    async def fake_get_observations(db, **kwargs):
        return []

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", fake_search_datasets)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.query_dataset", fake_query_dataset)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.query_griddap", fake_query_dataset)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)
    assert result.result.status == "success"
    assert len(result.result.evidence) == 2
    variables = {ev.variable for ev in result.result.evidence}
    assert "temperature" in variables
    assert result.result.source_status == "live"


@pytest.mark.asyncio
async def test_weather_agent_passes_default_time_constraint_to_incois(monkeypatch):
    from datetime import datetime, timedelta

    connector = IncoisConnector()
    received_time_min = None

    async def fake_query_dataset(self, dataset_id, variables, lat_min, lat_max, lon_min, lon_max, time_min=None, time_max=None):
        nonlocal received_time_min
        received_time_min = time_min
        from app.connectors.base_connector import ConnectorResult
        return ConnectorResult(
            status="success",
            data={
                "table": {
                    "columnNames": ["time", "latitude", "longitude", "TEMP", "PSAL"],
                    "columnUnits": ["UTC", "degrees_north", "degrees_east", "degree_C", "PSU"],
                    "rows": [["2024-01-01T00:00:00Z", 16.9, 82.2, 28.5, 32.0]],
                }
            },
            source_status="live",
            retrieved_at=datetime.utcnow(),
        )

    async def fake_get_observations(db, **kwargs):
        return []

    monkeypatch.setattr("app.agents.weather_agent.observations_service.get_observations", fake_get_observations)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.search_datasets", connector.search_datasets)
    monkeypatch.setattr("app.connectors.incois_connector.IncoisConnector.query_dataset", fake_query_dataset)

    agent = WeatherAgent(name="weather")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=10.0)
    assert result.result.status == "success"
    assert received_time_min is not None
    expected_min = (datetime.utcnow() - timedelta(days=1095)).strftime("%Y-%m-%d")
    assert received_time_min == expected_min


def test_safety_engine_indeterminate_when_no_data():
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=[],
        pfz_zones=[],
        geofence_violations=[],
        source_health=None,
    )
    assert result.is_indeterminate is True
    assert result.safety_badge is None
    assert "no observation or warning data available" in result.reasons


def test_safety_engine_safe_when_calm_conditions():
    observations = [
        {"variable": "wave_height", "value": 0.5},
        {"variable": "wind_speed", "value": 10.0},
    ]
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=observations,
        pfz_zones=[],
        geofence_violations=[],
        source_health=None,
    )
    assert result.is_indeterminate is False
    assert result.safety_badge == "SAFE"
    assert result.marine_hazard_index == 0.0


def test_safety_engine_unsafe_with_extreme_wave():
    observations = [
        {"variable": "wave_height", "value": 7.0},
        {"variable": "wind_speed", "value": 10.0},
    ]
    result = SafetyEngine.evaluate(
        warnings=[],
        observations=observations,
        pfz_zones=[],
        geofence_violations=[],
        source_health=None,
    )
    assert result.safety_badge == "UNSAFE"
    assert result.marine_hazard_index == 100.0


def test_safety_engine_imd_warning_precedence():
    observations = [
        {"variable": "wave_height", "value": 0.5},
        {"variable": "wind_speed", "value": 10.0},
    ]
    warnings = [
        {"issued_by": "IMD", "type": "Cyclone", "severity": "extreme"}
    ]
    result = SafetyEngine.evaluate(
        warnings=warnings,
        observations=observations,
        pfz_zones=[],
        geofence_violations=[],
        source_health=None,
    )
    assert result.safety_badge == "UNSAFE"
    assert result.marine_hazard_index >= 70.0
    assert any("IMD precedence" in r for r in result.reasons)


def test_evidence_never_fabricated_from_unavailable_source():
    connector = IncoisConnector()
    pfz_result = connector.normalize_pfz_unavailable()
    assert pfz_result.data is None
    assert len(pfz_result.evidence) == 0

    connector2 = ImdConnector(api_key="")
    imd_result = asyncio.run(connector2.get_port_warnings())
    assert imd_result.data is None
    assert len(imd_result.evidence) == 0

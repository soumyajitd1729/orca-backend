from unittest.mock import AsyncMock, patch

import pytest

from app.agents.route_agent import RouteAgent
from app.schemas.agent import AgentResultData


class FakeRouteEvaluation:
    def __init__(self, route_cost, risk_level, geofence_violations, hazard_warnings):
        self.route_cost = route_cost
        self.risk_level = risk_level
        self.geofence_violations = geofence_violations
        self.hazard_warnings = hazard_warnings

    def model_dump(self):
        return {
            "route_cost": self.route_cost,
            "risk_level": self.risk_level,
            "geofence_violations": self.geofence_violations,
            "hazard_warnings": self.hazard_warnings,
        }


@pytest.mark.asyncio
async def test_route_agent_success(monkeypatch):
    fake_eval = FakeRouteEvaluation(
        route_cost=125.5,
        risk_level="low",
        geofence_violations=[],
        hazard_warnings=[],
    )

    async def fake_evaluate_route(db, waypoints, vessel_type, max_wave_height):
        return fake_eval

    monkeypatch.setattr("app.agents.route_agent.route_service.evaluate_route", fake_evaluate_route)

    agent = RouteAgent(name="route")
    db = AsyncMock()
    waypoints = [
        {"lat": 13.0827, "lon": 80.2707},
        {"lat": 17.6868, "lon": 83.2185},
    ]
    result = await agent.run(db=db, waypoints=waypoints)
    assert isinstance(result.result, AgentResultData)
    assert result.result.status == "success"
    assert result.result.data["route_cost"] == 125.5
    assert result.result.data["risk_level"] == "low"
    assert result.result.source_status == "live"
    assert result.result.duration_ms is not None and result.result.duration_ms >= 0


@pytest.mark.asyncio
async def test_route_agent_invalid_route():
    agent = RouteAgent(name="route")
    db = AsyncMock()
    result = await agent.run(db=db, waypoints=[{"lat": 13.0827, "lon": 80.2707}])
    assert result.result.status == "error"
    assert result.result.data is None
    assert len(result.result.errors) > 0


@pytest.mark.asyncio
async def test_route_agent_unavailable(monkeypatch):
    async def fake_evaluate_route(db, waypoints, vessel_type, max_wave_height):
        raise RuntimeError("DB down")

    monkeypatch.setattr("app.agents.route_agent.route_service.evaluate_route", fake_evaluate_route)

    agent = RouteAgent(name="route")
    db = AsyncMock()
    waypoints = [
        {"lat": 13.0827, "lon": 80.2707},
        {"lat": 17.6868, "lon": 83.2185},
    ]
    result = await agent.run(db=db, waypoints=waypoints)
    assert result.result.status == "unavailable"
    assert result.result.data is None
    assert len(result.result.errors) > 0


@pytest.mark.asyncio
async def test_route_agent_violations_and_warnings(monkeypatch):
    fake_eval = FakeRouteEvaluation(
        route_cost=50.0,
        risk_level="high",
        geofence_violations=[{"id": "mpa-1", "name": "Gulf of Mannar"}],
        hazard_warnings=[{"id": "warn-1", "type": "cyclone", "severity": "high"}],
    )

    async def fake_evaluate_route(db, waypoints, vessel_type, max_wave_height):
        return fake_eval

    monkeypatch.setattr("app.agents.route_agent.route_service.evaluate_route", fake_evaluate_route)

    agent = RouteAgent(name="route")
    db = AsyncMock()
    waypoints = [
        {"lat": 9.5, "lon": 79.5},
        {"lat": 9.8, "lon": 80.2},
    ]
    result = await agent.run(db=db, waypoints=waypoints)
    assert result.result.status == "success"
    assert result.result.data["risk_level"] == "high"
    assert len(result.result.data["geofence_violations"]) == 1
    assert len(result.result.data["hazard_warnings"]) == 1


@pytest.mark.asyncio
async def test_route_agent_evidence_generation(monkeypatch):
    fake_eval = FakeRouteEvaluation(
        route_cost=75.0,
        risk_level="medium",
        geofence_violations=[],
        hazard_warnings=[],
    )

    async def fake_evaluate_route(db, waypoints, vessel_type, max_wave_height):
        return fake_eval

    monkeypatch.setattr("app.agents.route_agent.route_service.evaluate_route", fake_evaluate_route)

    agent = RouteAgent(name="route")
    db = AsyncMock()
    waypoints = [
        {"lat": 13.0827, "lon": 80.2707},
        {"lat": 17.6868, "lon": 83.2185},
    ]
    result = await agent.run(db=db, waypoints=waypoints)
    assert len(result.result.evidence) >= 2
    variables = [e.variable for e in result.result.evidence]
    assert "route_cost" in variables
    assert "risk_level" in variables

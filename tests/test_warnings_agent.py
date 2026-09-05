from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.warnings_agent import WarningsAgent
from app.schemas.agent import AgentResultData


class FakeWarning:
    def __init__(self, type, severity, issued_by, valid_from, valid_to):
        self.id = "warn-1"
        self.type = type
        self.severity = severity
        self.geometry = None
        self.issued_by = issued_by
        self.valid_from = valid_from
        self.valid_to = valid_to

    def model_dump(self):
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity.value if hasattr(self.severity, "value") else self.severity,
            "geometry": self.geometry,
            "issued_by": self.issued_by,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
        }


@pytest.mark.asyncio
async def test_warnings_agent_warnings_found(monkeypatch):
    from app.models.enums import WarningSeverity
    fake_warnings = [
        FakeWarning(
            "cyclone",
            WarningSeverity.high,
            "IMD",
            datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=1),
            datetime.now(timezone.utc) + __import__("datetime").timedelta(hours=1),
        ),
    ]

    async def fake_get_warnings(db, lat, lon, radius_km):
        return fake_warnings

    monkeypatch.setattr(
        "app.agents.warnings_agent.warnings_service.get_active_warnings_within_radius",
        fake_get_warnings,
    )

    agent = WarningsAgent(name="warnings")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=50.0)
    assert isinstance(result.result, AgentResultData)
    assert result.result.status == "success"
    assert len(result.result.data) == 1
    assert len(result.result.evidence) == 1
    assert result.result.source_status == "live"


@pytest.mark.asyncio
async def test_warnings_agent_no_warnings(monkeypatch):
    async def fake_get_warnings(db, lat, lon, radius_km):
        return []

    monkeypatch.setattr(
        "app.agents.warnings_agent.warnings_service.get_active_warnings_within_radius",
        fake_get_warnings,
    )

    agent = WarningsAgent(name="warnings")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=50.0)
    assert result.result.status == "no_data"
    assert result.result.data == []
    assert result.result.evidence == []


@pytest.mark.asyncio
async def test_warnings_agent_unavailable(monkeypatch):
    async def fake_get_warnings(db, lat, lon, radius_km):
        raise RuntimeError("DB down")

    monkeypatch.setattr(
        "app.agents.warnings_agent.warnings_service.get_active_warnings_within_radius",
        fake_get_warnings,
    )

    agent = WarningsAgent(name="warnings")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=50.0)
    assert result.result.status == "unavailable"
    assert result.result.data is None
    assert len(result.result.errors) > 0


@pytest.mark.asyncio
async def test_warnings_agent_radius_filtering(monkeypatch):
    from app.models.enums import WarningSeverity

    async def fake_get_warnings(db, lat, lon, radius_km):
        assert radius_km == 100.0
        return []

    monkeypatch.setattr(
        "app.agents.warnings_agent.warnings_service.get_active_warnings_within_radius",
        fake_get_warnings,
    )

    agent = WarningsAgent(name="warnings")
    db = AsyncMock()
    await agent.run(db=db, lat=16.9, lon=82.2, radius_km=100.0)


@pytest.mark.asyncio
async def test_warnings_agent_imd_warning_preserved(monkeypatch):
    from app.models.enums import WarningSeverity
    fake_warnings = [
        FakeWarning(
            "cyclone",
            WarningSeverity.extreme,
            "IMD",
            datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=1),
            datetime.now(timezone.utc) + __import__("datetime").timedelta(hours=1),
        ),
    ]

    async def fake_get_warnings(db, lat, lon, radius_km):
        return fake_warnings

    monkeypatch.setattr(
        "app.agents.warnings_agent.warnings_service.get_active_warnings_within_radius",
        fake_get_warnings,
    )

    agent = WarningsAgent(name="warnings")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=50.0)
    assert result.result.status == "success"
    assert len(result.result.data) == 1
    assert result.result.data[0]["issued_by"] == "IMD"


@pytest.mark.asyncio
async def test_warnings_agent_evidence_generation(monkeypatch):
    from app.models.enums import WarningSeverity
    fake_warnings = [
        FakeWarning(
            "storm",
            WarningSeverity.moderate,
            "IMD",
            datetime.now(timezone.utc) - __import__("datetime").timedelta(hours=1),
            datetime.now(timezone.utc) + __import__("datetime").timedelta(hours=1),
        ),
    ]

    async def fake_get_warnings(db, lat, lon, radius_km):
        return fake_warnings

    monkeypatch.setattr(
        "app.agents.warnings_agent.warnings_service.get_active_warnings_within_radius",
        fake_get_warnings,
    )

    agent = WarningsAgent(name="warnings")
    db = AsyncMock()
    result = await agent.run(db=db, lat=16.9, lon=82.2, radius_km=50.0)
    assert len(result.result.evidence) == 1
    assert result.result.evidence[0].source == "IMD"
    assert result.result.evidence[0].variable == "warning"
    assert result.result.evidence[0].value == "storm"
    assert result.result.evidence[0].unit == "advisory"

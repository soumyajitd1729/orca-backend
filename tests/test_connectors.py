from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.base_connector import BaseConnector, ConnectorEvidence, ConnectorResult
from app.connectors.imd_connector import ImdConnector
from app.connectors.incois_connector import IncoisConnector, INCOIS_OSF_URL
from app.connectors.mosdac_connector import MosdacConnector
from app.config import Settings


def test_base_connector_initialization():
    class ConcreteConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            return {}

    connector = ConcreteConnector.__new__(ConcreteConnector)
    connector.base_url = "https://example.com"
    connector.timeout = 5.0
    connector.max_retries = 3
    assert connector.base_url == "https://example.com"
    assert connector.timeout == 5.0
    assert connector.max_retries == 3


@pytest.mark.asyncio
async def test_incois_connector_search_datasets_success():
    mock_response = {
        "table": {
            "columns": [{"name": "datasetId"}, {"name": "Title"}],
            "rows": [["incois_sst_1", "INCOIS SST"]],
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch.object(mock_client, "__aenter__", AsyncMock(return_value=mock_client)):
            with patch.object(mock_client, "__aexit__", AsyncMock(return_value=False)):
                connector = IncoisConnector()
                result = await connector.search_datasets("sst")

    assert result.status == "success"
    assert result.source_status == "live"
    assert result.data == mock_response
    assert result.retrieved_at is not None


@pytest.mark.asyncio
async def test_incois_connector_search_datasets_failure():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.raise_for_status = MagicMock(side_effect=Exception("Server error"))

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch.object(mock_client, "__aenter__", AsyncMock(return_value=mock_client)):
            with patch.object(mock_client, "__aexit__", AsyncMock(return_value=False)):
                connector = IncoisConnector()
                result = await connector.search_datasets("sst")

    assert result.status == "error"
    assert result.source_status == "unavailable"
    assert len(result.errors) > 0


def test_incois_connector_normalize_observations_with_rows():
    connector = IncoisConnector()
    raw = {
        "table": {
            "columns": [
                {"name": "variable"},
                {"name": "value"},
                {"name": "unit"},
                {"name": "time"},
            ],
            "rows": [["sst", "28.5", "celsius", "2024-01-01T00:00:00Z"]],
        }
    }
    result = connector.normalize_observations(raw)
    assert result.status == "success"
    assert len(result.evidence) == 1
    assert result.evidence[0].source == "incois"
    assert result.evidence[0].variable == "sst"
    assert result.evidence[0].value == "28.5"
    assert result.evidence[0].unit == "celsius"
    assert result.evidence[0].url_ref.startswith("https://erddap.incois.gov.in")


def test_incois_connector_normalize_observations_empty():
    connector = IncoisConnector()
    result = connector.normalize_observations({"table": {"columns": [], "rows": []}})
    assert result.status == "no_data"
    assert result.source_status == "no_data"


def test_incois_connector_normalize_warnings():
    connector = IncoisConnector()
    raw = [
        {"type": "High Wave", "valid_from": "2024-01-01T00:00:00Z", "severity": "high"},
        {"type": "Swell Surge", "valid_from": "2024-01-02T00:00:00Z", "severity": "moderate"},
    ]
    result = connector.normalize_warnings(raw)
    assert result.status == "success"
    assert len(result.evidence) == 2
    assert result.evidence[0].variable == "high_wave"
    assert result.evidence[0].url_ref == INCOIS_OSF_URL


def test_incois_connector_pfz_unavailable():
    connector = IncoisConnector()
    result = connector.normalize_pfz_unavailable()
    assert result.status == "unavailable"
    assert result.source_status == "unavailable"
    assert len(result.errors) > 0
    assert "pfz_unavailable" in result.errors[0]


@pytest.mark.asyncio
async def test_mosdac_connector_search_datasets():
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=MagicMock(text="<html>mock</html>"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch.object(mock_client, "__aenter__", AsyncMock(return_value=mock_client)):
            with patch.object(mock_client, "__aexit__", AsyncMock(return_value=False)):
                connector = MosdacConnector(username="user", password="pass")
                result = await connector.search_datasets("SST")

    assert result.status == "success"
    assert result.source_status == "live"


def test_mosdac_connector_normalize_sst():
    connector = MosdacConnector(username="user", password="pass")
    raw = [
        {"value": 29.1, "time": "2024-01-01T00:00:00Z", "datasetId": "TEST_SST"},
    ]
    result = connector.normalize_sst(raw)
    assert result.status == "success"
    assert len(result.evidence) == 1
    assert result.evidence[0].source == "mosdac"
    assert result.evidence[0].variable == "sst"
    assert result.evidence[0].value == 29.1
    assert result.evidence[0].unit == "celsius"


def test_mosdac_connector_no_credentials():
    connector = MosdacConnector(username="", password="")
    assert connector.username == ""
    assert connector.password == ""


@pytest.mark.asyncio
async def test_imd_connector_without_api_key():
    connector = ImdConnector(api_key="")
    result = await connector.get_port_warnings()
    assert result.status == "unavailable"
    assert result.source_status == "unavailable"
    assert any("imd_not_configured" in e for e in result.errors)


def test_imd_connector_normalize_warnings():
    connector = ImdConnector(api_key="test-key")
    raw = [
        {
            "type": "Heavy Rain",
            "Date of Issue": "2024-01-01",
            "Day_1": "Heavy Rain",
            "Day1_Color": "#FF0000",
        }
    ]
    result = connector.normalize_warnings(raw, variable_prefix="district_warning")
    assert result.status == "success"
    assert len(result.evidence) == 1
    assert result.evidence[0].source == "imd"
    assert result.evidence[0].variable == "heavy_rain"
    assert result.evidence[0].url_ref == "https://api.imd.gov.in/public/api_reference.html"


def test_imd_connector_normalize_observations():
    connector = ImdConnector(api_key="test-key")
    raw = [
        {
            "CURR_TEMP": "32.5",
            "WIND_SPEED": "15",
            "TIME": "07:00:00",
            "DATE": "2024-01-01",
        }
    ]
    result = connector.normalize_observations(raw)
    assert result.status == "success"
    assert len(result.evidence) == 2
    variables = {e.variable for e in result.evidence}
    assert "temperature" in variables
    assert "wind_speed" in variables


@pytest.mark.asyncio
async def test_connector_retry_on_timeout():
    class FlakyConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            raise asyncio.TimeoutError()

        def normalize(self, raw, **kwargs):
            return ConnectorResult(status="error")

    connector = FlakyConnector.__new__(FlakyConnector)
    connector.base_url = "https://example.com"
    connector.timeout = 0.1
    connector.max_retries = 1

    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
        result = await connector.fetch()

    assert result.status == "error"
    assert result.source_status == "unavailable"
    assert len(result.errors) > 0


@pytest.mark.asyncio
async def test_connector_retry_on_exception():
    class FailingConnector(BaseConnector):
        async def _fetch_data(self, **kwargs):
            raise RuntimeError("boom")

        def normalize(self, raw, **kwargs):
            return ConnectorResult(status="error")

    connector = FailingConnector.__new__(FailingConnector)
    connector.base_url = "https://example.com"
    connector.timeout = 1.0
    connector.max_retries = 1

    result = await connector.fetch()

    assert result.status == "error"
    assert result.source_status == "unavailable"
    assert "boom" in result.errors[0]

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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
    assert result.evidence[0].source == "incois"


def test_incois_connector_normalize_observations_empty():
    connector = IncoisConnector()
    result = connector.normalize_observations({"table": {"columns": [], "rows": []}})
    assert result.status == "no_data"
    assert result.source_status == "no_data"


@pytest.mark.asyncio
async def test_incois_connector_query_dataset_no_matching_results():
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.text = 'Error {\n    code=404;\n    message="Not Found: Your query produced no matching results. (nRows = 0)";\n}'
    mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError("404", request=None, response=mock_resp))

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch.object(mock_client, "__aenter__", AsyncMock(return_value=mock_client)):
            with patch.object(mock_client, "__aexit__", AsyncMock(return_value=False)):
                connector = IncoisConnector()
                result = await connector.query_dataset(
                    dataset_id="test_dataset",
                    variables=["TEMP"],
                    lat_min=10.0,
                    lat_max=11.0,
                    lon_min=20.0,
                    lon_max=21.0,
                    time_min="2099-01-01",
                )

    assert result.status == "no_data"
    assert result.source_status == "no_data"
    assert "incois_query_no_matching_results" in result.errors


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
async def test_imd_connector_open_meteo_current_weather_source_label():
    connector = ImdConnector(api_key="")
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "current_weather": {
                "temperature": 26.4,
                "windspeed": 12.0,
                "winddirection": 180.0,
            }
        })
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await connector.get_current_weather(lat=16.94, lon=82.24)

    assert result.status == "success"
    assert len(result.evidence) >= 1
    assert result.source_status == "live"
    for ev in result.evidence:
        assert ev.source == "open_meteo"
        assert ev.url_ref == "https://api.open-meteo.com/v1/forecast"


@pytest.mark.asyncio
async def test_imd_connector_open_meteo_forecast_tomorrow_morning():
    connector = ImdConnector(api_key="")
    tomorrow = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    hourly_times = [f"{tomorrow}T{hour:02d}:00" for hour in range(24)]
    hourly_data = {
        "time": hourly_times,
        "temperature_2m": [25.0 + i * 0.5 for i in range(24)],
        "relative_humidity_2m": [70 + i for i in range(24)],
        "windspeed_10m": [10.0 + i * 0.2 for i in range(24)],
        "winddirection_10m": [180.0 + i for i in range(24)],
        "weather_code": [1 for _ in range(24)],
        "precipitation": [0.0 for _ in range(24)],
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"hourly": hourly_data})
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await connector.get_current_weather(
            lat=16.94, lon=82.24, time_expression="tomorrow_morning"
        )

    assert result.status == "success"
    assert len(result.evidence) == 36
    for ev in result.evidence:
        assert ev.source == "open_meteo"
        assert ev.valid_time is not None
    variables = {e.variable for e in result.evidence}
    assert "temperature" in variables
    assert "humidity" in variables
    assert "wind_speed" in variables
    assert "wind_direction" in variables
    assert "weather_code" in variables
    assert "rainfall" in variables


@pytest.mark.asyncio
async def test_imd_connector_open_meteo_failure_returns_error():
    connector = ImdConnector(api_key="")
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError("500", request=None, response=mock_resp))
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await connector.get_current_weather(lat=16.94, lon=82.24)

    assert result.status == "error"
    assert result.source_status == "unavailable"
    for ev in result.evidence:
        assert ev.source != "imd"
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


def test_incois_select_observation_dataset_from_list_prefers_tabledap():
    connector = IncoisConnector()
    search_result = ConnectorResult(
        status="success",
        data=[
            {"datasetID": "griddap_set", "url": "/erddap/griddap/griddap_set.html"},
            {"datasetID": "tabledap_set", "url": "/erddap/tabledap/tabledap_set.html"},
        ],
        source_status="live",
    )
    result = connector.select_observation_dataset(search_result)
    assert result is not None
    assert result["dataset_id"] == "tabledap_set"
    assert result["access_method"] == "tabledap"


def test_incois_select_observation_dataset_from_list_falls_back_to_griddap():
    connector = IncoisConnector()
    search_result = ConnectorResult(
        status="success",
        data=[
            {"datasetID": "griddap_set", "url": "/erddap/griddap/griddap_set.html"},
        ],
        source_status="live",
    )
    result = connector.select_observation_dataset(search_result)
    assert result is not None
    assert result["dataset_id"] == "griddap_set"
    assert result["access_method"] == "griddap"


def test_incois_select_observation_dataset_list_skips_alldatasets():
    connector = IncoisConnector()
    search_result = ConnectorResult(
        status="success",
        data=[
            {"datasetID": "allDatasets", "url": "/erddap/tabledap/alldatasets.html"},
            {"datasetID": "tabledap_set", "url": "/erddap/tabledap/tabledap_set.html"},
        ],
        source_status="live",
    )
    result = connector.select_observation_dataset(search_result)
    assert result is not None
    assert result["dataset_id"] == "tabledap_set"


def test_incois_select_observation_dataset_list_no_match():
    connector = IncoisConnector()
    search_result = ConnectorResult(
        status="success",
        data=[
            {"datasetID": "allDatasets", "url": "/erddap/tabledap/alldatasets.html"},
        ],
        source_status="live",
    )
    result = connector.select_observation_dataset(search_result)
    assert result is None


def test_incois_select_observation_dataset_malformed_response():
    connector = IncoisConnector()
    assert connector.select_observation_dataset(ConnectorResult(status="success", data=None)) is None
    assert connector.select_observation_dataset(ConnectorResult(status="success", data="not_a_list")) is None
    assert connector.select_observation_dataset(ConnectorResult(status="success", data=123)) is None
    assert connector.select_observation_dataset(ConnectorResult(status="success", data=[])) is None
    assert connector.select_observation_dataset(ConnectorResult(status="success", data=[{"not_a_dataset": 1}])) is None


def test_incois_select_observation_dataset_legacy_dict_format_still_works():
    connector = IncoisConnector()
    search_result = ConnectorResult(
        status="success",
        data={
            "table": {
                "rows": [
                    ["incois_sst_1", "INCOIS SST", "/erddap/tabledap/incois_sst_1.html"],
                ]
            }
        },
        source_status="live",
    )
    result = connector.select_observation_dataset(search_result)
    assert result is not None
    assert result["dataset_id"] == "incois_sst_1"
    assert result["access_method"] == "tabledap"


@pytest.mark.asyncio
async def test_incois_weather_agent_integration_with_list_search_response():
    mock_search_result = ConnectorResult(
        status="success",
        data=[
            {"datasetID": "incois_sst_2024", "url": "/erddap/tabledap/incois_sst_2024.html"},
        ],
        source_status="live",
    )

    mock_query_result = ConnectorResult(
        status="success",
        data={
            "table": {
                "columnNames": ["time", "latitude", "longitude", "TEMP", "PSAL"],
                "columnUnits": ["", "degrees_north", "degrees_east", "degree_C", "PSU"],
                "rows": [
                    ["2024-01-01T00:00:00Z", 17.0, 83.0, 28.5, 32.0],
                ],
            }
        },
        evidence=[],
        source_status="live",
    )

    from app.agents.weather_agent import WeatherAgent

    with patch("app.agents.weather_agent.observations_service.get_observations", return_value=[]):
        with patch.object(IncoisConnector, "search_datasets", new_callable=AsyncMock, return_value=mock_search_result):
            with patch.object(IncoisConnector, "select_observation_dataset", return_value={"dataset_id": "incois_sst_2024", "access_method": "tabledap"}):
                with patch.object(IncoisConnector, "query_dataset", new_callable=AsyncMock, return_value=mock_query_result):
                    with patch.object(IncoisConnector, "normalize_observations", return_value=ConnectorResult(status="success", evidence=[], source_status="live")):
                        agent = WeatherAgent(name="weather")
                        result = await agent._execute(db=None, lat=17.0, lon=82.0, radius_km=10.0, variables=["TEMP", "PSAL"])

    assert result.status == "no_data"


def test_incois_select_observation_dataset_normalizes_full_url_dataset_id():
    connector = IncoisConnector()
    search_result = ConnectorResult(
        status="success",
        data=[
            {
                "datasetID": "https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.subset",
                "url": "https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.subset.html",
            },
        ],
        source_status="live",
    )
    result = connector.select_observation_dataset(search_result)
    assert result is not None
    assert result["dataset_id"] == "Indian_ARGO_Floats"
    assert result["access_method"] == "tabledap"


def test_incois_select_observation_dataset_normalizes_path_style_dataset_id():
    connector = IncoisConnector()
    search_result = ConnectorResult(
        status="success",
        data=[
            {
                "datasetID": "/erddap/tabledap/Indian_ARGO_Floats.subset.html",
                "url": "https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.subset.html",
            },
        ],
        source_status="live",
    )
    result = connector.select_observation_dataset(search_result)
    assert result is not None
    assert result["dataset_id"] == "Indian_ARGO_Floats"


@pytest.mark.asyncio
async def test_incois_query_dataset_regression_full_url_dataset_id():
    connector = IncoisConnector()
    connector.base_url = "https://erddap.incois.gov.in/erddap"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"table": {"rows": [], "columnNames": [], "columnUnits": []}})
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await connector.query_dataset(
            dataset_id="https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.subset",
            variables=["TEMP"],
            lat_min=10.0,
            lat_max=11.0,
            lon_min=20.0,
            lon_max=21.0,
        )

    called_url = mock_client.get.call_args[0][0]
    assert called_url.startswith("https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.json")
    assert called_url.count("https://erddap.incois.gov.in/erddap") == 1


def test_incois_normalize_dataset_id_strips_subset_suffix():
    connector = IncoisConnector()
    assert connector._normalize_dataset_id("Indian_ARGO_Floats.subset") == "Indian_ARGO_Floats"
    assert connector._normalize_dataset_id("Indian_ARGO_Floats") == "Indian_ARGO_Floats"
    assert connector._normalize_dataset_id("https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.subset") == "Indian_ARGO_Floats"
    assert connector._normalize_dataset_id("/erddap/tabledap/Indian_ARGO_Floats.subset.html") == "Indian_ARGO_Floats"


@pytest.mark.asyncio
async def test_incois_argo_floats_subset_url_regression():
    connector = IncoisConnector()
    connector.base_url = "https://erddap.incois.gov.in/erddap"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"table": {"rows": [], "columnNames": [], "columnUnits": []}})
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await connector.query_dataset(
            dataset_id="Indian_ARGO_Floats.subset",
            variables=["TEMP", "PSAL"],
            lat_min=10.0,
            lat_max=11.0,
            lon_min=20.0,
            lon_max=21.0,
        )

    called_url = mock_client.get.call_args[0][0]
    assert called_url.startswith("https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.json?TEMP,PSAL")
    assert ".subset" not in called_url
    assert "&latitude>=10.0" in called_url
    assert "&longitude>=20.0" in called_url


@pytest.mark.asyncio
async def test_incois_query_griddap_does_not_double_concatenate_base_url():
    connector = IncoisConnector()
    connector.base_url = "https://erddap.incois.gov.in/erddap"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"table": {"rows": [], "columnNames": [], "columnUnits": []}})
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await connector.query_griddap(
            dataset_id="https://erddap.incois.gov.in/erddap/griddap/Indian_ARGO_Floats.subset",
            variables=["TEMP"],
            lat_min=10.0,
            lat_max=11.0,
            lon_min=20.0,
            lon_max=21.0,
        )

    called_url = mock_client.get.call_args[0][0]
    assert called_url.startswith("https://erddap.incois.gov.in/erddap/griddap/Indian_ARGO_Floats.json")
    assert called_url.count("https://erddap.incois.gov.in/erddap") == 1


def test_incois_end_to_end_production_url_bug():
    connector = IncoisConnector()
    connector.base_url = "https://erddap.incois.gov.in/erddap"

    search_result = ConnectorResult(
        status="success",
        data=[
            {
                "datasetID": "https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.subset",
                "url": "https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.subset.html",
            },
        ],
        source_status="live",
    )

    dataset_info = connector.select_observation_dataset(search_result)
    assert dataset_info is not None
    assert dataset_info["dataset_id"] == "Indian_ARGO_Floats"
    assert dataset_info["access_method"] == "tabledap"

    dataset_id = dataset_info["dataset_id"]
    normalized = connector._normalize_dataset_id(dataset_id)
    assert normalized == "Indian_ARGO_Floats"

    url = f"{connector.base_url}/tabledap/{normalized}.json"
    assert url == "https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.json"
    assert url.count("https://erddap.incois.gov.in/erddap") == 1


@pytest.mark.asyncio
async def test_incois_query_dataset_regression_full_url_dataset_id():
    connector = IncoisConnector()
    connector.base_url = "https://erddap.incois.gov.in/erddap"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"table": {"rows": [], "columnNames": [], "columnUnits": []}})
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await connector.query_dataset(
            dataset_id="https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.subset",
            variables=["TEMP"],
            lat_min=10.0,
            lat_max=11.0,
            lon_min=20.0,
            lon_max=21.0,
        )

    called_url = mock_client.get.call_args[0][0]
    assert called_url.startswith("https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.json")
    assert called_url.count("https://erddap.incois.gov.in/erddap") == 1


@pytest.mark.asyncio
async def test_incois_query_griddap_regression_full_url_dataset_id():
    connector = IncoisConnector()
    connector.base_url = "https://erddap.incois.gov.in/erddap"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"table": {"rows": [], "columnNames": [], "columnUnits": []}})
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await connector.query_griddap(
            dataset_id="https://erddap.incois.gov.in/erddap/griddap/Indian_ARGO_Floats.subset",
            variables=["TEMP"],
            lat_min=10.0,
            lat_max=11.0,
            lon_min=20.0,
            lon_max=21.0,
        )

    called_url = mock_client.get.call_args[0][0]
    assert called_url.startswith("https://erddap.incois.gov.in/erddap/griddap/Indian_ARGO_Floats.json")
    assert called_url.count("https://erddap.incois.gov.in/erddap") == 1


@pytest.mark.asyncio
async def test_incois_query_dataset_regression_full_url_dataset_id():
    connector = IncoisConnector()
    connector.base_url = "https://erddap.incois.gov.in/erddap"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"table": {"rows": [], "columnNames": [], "columnUnits": []}})
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        await connector.query_dataset(
            dataset_id="https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.subset",
            variables=["TEMP"],
            lat_min=10.0,
            lat_max=11.0,
            lon_min=20.0,
            lon_max=21.0,
        )

    called_url = mock_client.get.call_args[0][0]
    assert called_url.startswith("https://erddap.incois.gov.in/erddap/tabledap/Indian_ARGO_Floats.json")
    assert called_url.count("https://erddap.incois.gov.in/erddap") == 1

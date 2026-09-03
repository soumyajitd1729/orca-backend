from app.models.enums import QualityFlag
from app.schemas.observations import ObservationOut


async def test_observations_returns_list_within_envelope(client, monkeypatch):
    fake = [
        ObservationOut(
            id="00000000-0000-0000-0000-000000000001",
            variable="sst",
            value=28.5,
            unit="celsius",
            geometry={"type": "Point", "coordinates": [82.2, 16.9]},
            observed_at="2026-01-01T00:00:00+00:00",
            source_time="2026-01-01T00:05:00+00:00",
            source_id="00000000-0000-0000-0000-000000000010",
            quality_flag=QualityFlag.good,
            confidence=0.95,
        )
    ]

    async def fake_get(db, **kwargs):
        return fake

    monkeypatch.setattr("app.services.observations_service.get_observations", fake_get)

    resp = await client.get(
        "/api/v1/observations",
        params={"variable": "sst", "lat": 16.9, "lon": 82.2, "radius_km": 50},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["variable"] == "sst"
    assert item["value"] == 28.5
    assert item["unit"] == "celsius"
    assert item["quality_flag"] == "good"
    assert item["confidence"] == 0.95
    assert item["geometry"]["type"] == "Point"
    assert "request_id" in body["meta"]


async def test_observations_empty_results_returns_empty_list(client, monkeypatch):
    async def fake_get(db, **kwargs):
        return []

    monkeypatch.setattr("app.services.observations_service.get_observations", fake_get)

    resp = await client.get(
        "/api/v1/observations",
        params={"variable": "sst", "lat": 16.9, "lon": 82.2, "radius_km": 50},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["data"] == []
    assert "request_id" in body["meta"]


async def test_observations_service_error_returns_500(client, monkeypatch):
    async def fake_get(db, **kwargs):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.services.observations_service.get_observations", fake_get)

    resp = await client.get(
        "/api/v1/observations",
        params={"variable": "sst", "lat": 16.9, "lon": 82.2, "radius_km": 50},
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0
    assert "request_id" in body["meta"]


async def test_observations_invalid_lat_returns_422(client):
    resp = await client.get(
        "/api/v1/observations",
        params={"variable": "sst", "lat": 999.0, "lon": 82.2, "radius_km": 50},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_observations_invalid_lon_returns_422(client):
    resp = await client.get(
        "/api/v1/observations",
        params={"variable": "sst", "lat": 16.9, "lon": -999.0, "radius_km": 50},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_observations_filters_by_variable_and_quality_flag(client, monkeypatch):
    captured = {}

    async def fake_get(db, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("app.services.observations_service.get_observations", fake_get)

    resp = await client.get(
        "/api/v1/observations",
        params={
            "variable": "chlorophyll",
            "quality_flag": "good",
            "source_id": "00000000-0000-0000-0000-000000000010",
            "lat": 16.9,
            "lon": 82.2,
            "radius_km": 25,
        },
    )
    assert resp.status_code == 200
    assert captured["variable"] == "chlorophyll"
    assert captured["quality_flag"] == QualityFlag.good
    assert str(captured["source_id"]) == "00000000-0000-0000-0000-000000000010"
    assert captured["lat"] == 16.9
    assert captured["lon"] == 82.2
    assert captured["radius_km"] == 25


async def test_observations_envelope_contains_meta_fields(client, monkeypatch):
    async def fake_get(db, **kwargs):
        return []

    monkeypatch.setattr("app.services.observations_service.get_observations", fake_get)

    resp = await client.get(
        "/api/v1/observations",
        params={"variable": "sst", "lat": 16.9, "lon": 82.2, "radius_km": 50},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]
    assert body["errors"] == []

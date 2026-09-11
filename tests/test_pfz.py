from datetime import datetime, timezone

import pytest

from app.schemas.pfz import PFZZoneOut


async def test_pfz_zones_returns_list_within_envelope(client, monkeypatch):
    fake = [
        PFZZoneOut(
            id="00000000-0000-0000-0000-000000000001",
            geometry={"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
            score=None,
            components={"source_type": "incois_pfz_advisory"},
            valid_time="2026-01-01T00:00:00+00:00",
            source_type="incois_pfz_advisory",
            source_name="INCOIS PFZ Advisory",
            sector="SOUTH ANDHRA PRADESH",
            landing_center="Machilipatnam",
            depth="50-80m",
            distance_km=15.0,
            direction="SW",
            forecast_date="2026-01-01",
            valid_until="2026-01-02",
        )
    ]

    async def fake_get(lat, lon, radius_km, db):
        return fake

    monkeypatch.setattr("app.services.pfz_service.get_pfz_zones", fake_get)

    resp = await client.get(
        "/api/v1/pfz-zones", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["score"] is None
    assert item["source_type"] == "incois_pfz_advisory"
    assert item["sector"] == "SOUTH ANDHRA PRADESH"
    assert item["components"]["source_type"] == "incois_pfz_advisory"
    assert item["geometry"]["type"] == "Polygon"
    assert "request_id" in body["meta"]


async def test_pfz_zones_requires_query_params(client):
    resp = await client.get("/api/v1/pfz-zones")
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_pfz_zones_empty_results_returns_empty_list(client, monkeypatch):
    async def fake_get(lat, lon, radius_km, db):
        return []

    monkeypatch.setattr("app.services.pfz_service.get_pfz_zones", fake_get)

    resp = await client.get(
        "/api/v1/pfz-zones", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["data"] == []
    assert "request_id" in body["meta"]


async def test_pfz_zones_service_error_returns_500(client, monkeypatch):
    async def fake_get(lat, lon, radius_km, db):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.services.pfz_service.get_pfz_zones", fake_get)

    resp = await client.get(
        "/api/v1/pfz-zones", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0
    assert "request_id" in body["meta"]


async def test_pfz_zones_invalid_lat_returns_422(client):
    resp = await client.get(
        "/api/v1/pfz-zones", params={"lat": 999.0, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_pfz_zones_invalid_lon_returns_422(client):
    resp = await client.get(
        "/api/v1/pfz-zones", params={"lat": 16.9, "lon": -999.0, "radius_km": 50}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_pfz_zones_envelope_contains_meta_fields(client, monkeypatch):
    async def fake_get(lat, lon, radius_km, db):
        return []

    monkeypatch.setattr("app.services.pfz_service.get_pfz_zones", fake_get)

    resp = await client.get(
        "/api/v1/pfz-zones", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]
    assert body["errors"] == []


async def test_pfz_zones_preserves_source_metadata(client, monkeypatch):
    fake = [
        PFZZoneOut(
            id="00000000-0000-0000-0000-000000000002",
            geometry=None,
            score=None,
            components={"source_type": "incois_pfz_advisory", "reference": "manual_snapshot"},
            valid_time="2026-09-10T00:00:00+00:00",
            source_type="incois_pfz_advisory",
            source_name="INCOIS PFZ Advisory",
            sector="SOUTH ANDHRA PRADESH",
            landing_center="Machilipatnam",
            depth="50-80m",
            distance_km=15.0,
            direction="SW",
            forecast_date="2026-09-10",
            valid_until="2026-09-11",
        )
    ]

    async def fake_get(lat, lon, radius_km, db):
        return fake

    monkeypatch.setattr("app.services.pfz_service.get_pfz_zones", fake_get)

    resp = await client.get(
        "/api/v1/pfz-zones", params={"lat": 16.94, "lon": 82.24, "radius_km": 25}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["source_type"] == "incois_pfz_advisory"
    assert item["sector"] == "SOUTH ANDHRA PRADESH"
    assert item["landing_center"] == "Machilipatnam"
    assert item["depth"] == "50-80m"
    assert item["distance_km"] == 15.0
    assert item["direction"] == "SW"
    assert item["forecast_date"] == "2026-09-10"
    assert item["valid_until"] == "2026-09-11"
    assert item["score"] is None

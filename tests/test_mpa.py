from app.schemas.mpa import MpaBoundaryOut


async def test_mpa_boundaries_returns_list_within_envelope(client, monkeypatch):
    fake = [
        MpaBoundaryOut(
            id="00000000-0000-0000-0000-000000000001",
            name="Gulf of Mannar",
            geometry={"type": "MultiPolygon", "coordinates": [[[[0, 0], [0, 1], [1, 1], [0, 0]]]]},
            source="MoES",
            version="1.0",
            effective_date="2025-01-01T00:00:00+00:00",
        )
    ]

    async def fake_get(lat, lon, radius_km, db):
        return fake

    monkeypatch.setattr("app.services.mpa_service.get_mpa_boundaries", fake_get)

    resp = await client.get(
        "/api/v1/mpa-boundaries", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["name"] == "Gulf of Mannar"
    assert item["source"] == "MoES"
    assert item["version"] == "1.0"
    assert item["geometry"]["type"] == "MultiPolygon"
    assert "request_id" in body["meta"]


async def test_mpa_boundaries_empty_results_returns_empty_list(client, monkeypatch):
    async def fake_get(lat, lon, radius_km, db):
        return []

    monkeypatch.setattr("app.services.mpa_service.get_mpa_boundaries", fake_get)

    resp = await client.get(
        "/api/v1/mpa-boundaries", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["data"] == []
    assert "request_id" in body["meta"]


async def test_mpa_boundaries_service_error_returns_500(client, monkeypatch):
    async def fake_get(lat, lon, radius_km, db):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.services.mpa_service.get_mpa_boundaries", fake_get)

    resp = await client.get(
        "/api/v1/mpa-boundaries", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0
    assert "request_id" in body["meta"]


async def test_mpa_boundaries_invalid_lat_returns_422(client):
    resp = await client.get(
        "/api/v1/mpa-boundaries", params={"lat": 999.0, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_mpa_boundaries_invalid_lon_returns_422(client):
    resp = await client.get(
        "/api/v1/mpa-boundaries", params={"lat": 16.9, "lon": -999.0, "radius_km": 50}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_mpa_boundaries_envelope_contains_meta_fields(client, monkeypatch):
    async def fake_get(lat, lon, radius_km, db):
        return []

    monkeypatch.setattr("app.services.mpa_service.get_mpa_boundaries", fake_get)

    resp = await client.get(
        "/api/v1/mpa-boundaries", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]
    assert body["errors"] == []

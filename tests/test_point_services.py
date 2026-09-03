from app.schemas.layers import LayerOut
from app.schemas.point import PointResponse


async def test_layers_returns_list_within_envelope(client):
    resp = await client.get("/api/v1/layers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 4
    ids = [layer["id"] for layer in body["data"]]
    assert "observations" in ids
    assert "pfz" in ids
    assert "warnings" in ids
    assert "mpa" in ids
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]


async def test_point_query_returns_aggregated_data(client, monkeypatch):
    fake = PointResponse(
        observations=[
            {
                "id": "obs-1",
                "variable": "sst",
                "value": 28.5,
                "unit": "celsius",
                "geometry": {"type": "Point", "coordinates": [82.2, 16.9]},
                "observed_at": "2026-01-01T00:00:00+00:00",
                "source_time": "2026-01-01T00:05:00+00:00",
                "source_id": "00000000-0000-0000-0000-000000000010",
                "quality_flag": "good",
                "confidence": 0.95,
            }
        ],
        warnings=[
            {
                "id": "warn-1",
                "type": "cyclone",
                "severity": "high",
                "description": "cyclone advisory issued by IMD",
                "issued_by": "IMD",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": "2026-12-31T00:00:00+00:00",
                "geometry": None,
            }
        ],
        pfz_zones=[
            {
                "id": "pfz-1",
                "score": 0.85,
                "components": {"sst": 28.5},
                "valid_time": "2026-01-01T00:00:00+00:00",
                "geometry": None,
            }
        ],
    )

    async def fake_get(db, lat, lon, radius_km):
        assert lat == 16.9
        assert lon == 82.2
        assert radius_km == 25.0
        return fake

    monkeypatch.setattr("app.services.point_service.get_point_data", fake_get)

    resp = await client.get(
        "/api/v1/marine/point", params={"lat": 16.9, "lon": 82.2, "radius_km": 25}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert len(body["data"]["observations"]) == 1
    assert body["data"]["observations"][0]["variable"] == "sst"
    assert len(body["data"]["warnings"]) == 1
    assert body["data"]["warnings"][0]["severity"] == "high"
    assert len(body["data"]["pfz_zones"]) == 1
    assert body["data"]["pfz_zones"][0]["score"] == 0.85
    assert "request_id" in body["meta"]


async def test_point_query_empty_results_returns_empty_lists(client, monkeypatch):
    fake = PointResponse(observations=[], warnings=[], pfz_zones=[])

    async def fake_get(db, lat, lon, radius_km):
        return fake

    monkeypatch.setattr("app.services.point_service.get_point_data", fake_get)

    resp = await client.get(
        "/api/v1/marine/point", params={"lat": 16.9, "lon": 82.2, "radius_km": 10}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["data"]["observations"] == []
    assert body["data"]["warnings"] == []
    assert body["data"]["pfz_zones"] == []
    assert "request_id" in body["meta"]


async def test_point_query_invalid_lat_returns_422(client):
    resp = await client.get(
        "/api/v1/marine/point", params={"lat": 999.0, "lon": 82.2, "radius_km": 10}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_point_query_invalid_lon_returns_422(client):
    resp = await client.get(
        "/api/v1/marine/point", params={"lat": 16.9, "lon": -999.0, "radius_km": 10}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_point_query_service_error_returns_500(client, monkeypatch):
    async def fake_get(db, lat, lon, radius_km):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.services.point_service.get_point_data", fake_get)

    resp = await client.get(
        "/api/v1/marine/point", params={"lat": 16.9, "lon": 82.2, "radius_km": 10}
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0
    assert "request_id" in body["meta"]

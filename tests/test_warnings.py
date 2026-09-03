from app.models.enums import WarningSeverity
from app.schemas.warnings import WarningOut


async def test_warnings_returns_list_within_envelope(client, monkeypatch):
    fake = [
        WarningOut(
            id="00000000-0000-0000-0000-000000000001",
            type="cyclone",
            title="cyclone",
            description="cyclone advisory issued by IMD",
            severity=WarningSeverity.high,
            geometry={"type": "Polygon", "coordinates": [[[0, 0], [0, 1], [1, 1], [0, 0]]]},
            issued_by="IMD",
            valid_from="2026-01-01T00:00:00+00:00",
            valid_to="2026-12-31T00:00:00+00:00",
        )
    ]

    async def fake_get(lat, lon, radius_km, db):
        return fake

    monkeypatch.setattr("app.services.warnings_service.get_warnings", fake_get)

    resp = await client.get(
        "/api/v1/warnings", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    item = body["data"][0]
    assert item["type"] == "cyclone"
    assert item["severity"] == "high"
    assert item["issued_by"] == "IMD"
    assert item["geometry"]["type"] == "Polygon"
    assert "request_id" in body["meta"]


async def test_warnings_requires_query_params(client):
    resp = await client.get("/api/v1/warnings")
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_warnings_empty_results_returns_empty_list(client, monkeypatch):
    async def fake_get(lat, lon, radius_km, db):
        return []

    monkeypatch.setattr("app.services.warnings_service.get_warnings", fake_get)

    resp = await client.get(
        "/api/v1/warnings", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["data"] == []
    assert "request_id" in body["meta"]


async def test_warnings_service_error_returns_500(client, monkeypatch):
    async def fake_get(lat, lon, radius_km, db):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.services.warnings_service.get_warnings", fake_get)

    resp = await client.get(
        "/api/v1/warnings", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0
    assert "request_id" in body["meta"]


async def test_warnings_severity_filter(client, monkeypatch):
    filtered = [
        WarningOut(
            id="00000000-0000-0000-0000-000000000002",
            type="tsunami",
            title="tsunami",
            description="tsunami advisory issued by INCOIS",
            severity=WarningSeverity.extreme,
            geometry=None,
            issued_by="INCOIS",
            valid_from="2026-01-01T00:00:00+00:00",
            valid_to="2026-12-31T00:00:00+00:00",
        )
    ]

    async def fake_get_by_severity(db, severity):
        return filtered

    monkeypatch.setattr(
        "app.services.warnings_service.get_warnings_by_severity", fake_get_by_severity
    )

    resp = await client.get(
        "/api/v1/warnings",
        params={"lat": 16.9, "lon": 82.2, "radius_km": 50, "severity": "extreme"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 1
    assert body["data"][0]["severity"] == "extreme"
    assert body["data"][0]["type"] == "tsunami"


async def test_warnings_invalid_lat_returns_422(client):
    resp = await client.get(
        "/api/v1/warnings", params={"lat": 999.0, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_warnings_invalid_lon_returns_422(client):
    resp = await client.get(
        "/api/v1/warnings", params={"lat": 16.9, "lon": -999.0, "radius_km": 50}
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_warnings_invalid_severity_returns_422(client):
    resp = await client.get(
        "/api/v1/warnings",
        params={"lat": 16.9, "lon": 82.2, "radius_km": 50, "severity": "invalid"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_warnings_envelope_contains_meta_fields(client, monkeypatch):
    async def fake_get(lat, lon, radius_km, db):
        return []

    monkeypatch.setattr("app.services.warnings_service.get_warnings", fake_get)

    resp = await client.get(
        "/api/v1/warnings", params={"lat": 16.9, "lon": 82.2, "radius_km": 50}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]
    assert body["errors"] == []
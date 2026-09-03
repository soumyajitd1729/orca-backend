from app.schemas.route import RouteEvaluationOut


async def test_route_evaluate_returns_envelope(client, monkeypatch):
    fake = RouteEvaluationOut(
        route_cost=120.5,
        risk_level="low",
        geofence_violations=[],
        hazard_warnings=[],
    )

    async def fake_evaluate(db, waypoints, vessel_type, max_wave_height):
        assert len(waypoints) == 2
        assert waypoints[0]["lat"] == 10.0
        assert waypoints[0]["lon"] == 76.0
        assert waypoints[1]["lat"] == 11.0
        assert waypoints[1]["lon"] == 77.0
        return fake

    monkeypatch.setattr("app.services.route_service.evaluate_route", fake_evaluate)

    resp = await client.post(
        "/api/v1/route/evaluate",
        json={
            "waypoints": [{"lat": 10.0, "lon": 76.0}, {"lat": 11.0, "lon": 77.0}],
            "vessel_type": "fishing_boat",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["data"]["route_cost"] == 120.5
    assert body["data"]["risk_level"] == "low"
    assert body["data"]["geofence_violations"] == []
    assert body["data"]["hazard_warnings"] == []
    assert "request_id" in body["meta"]


async def test_route_evaluate_single_waypoint_returns_422(client):
    resp = await client.post(
        "/api/v1/route/evaluate",
        json={"waypoints": [{"lat": 10.0, "lon": 76.0}]},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_route_evaluate_empty_waypoints_returns_422(client):
    resp = await client.post(
        "/api/v1/route/evaluate",
        json={"waypoints": []},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_route_evaluate_invalid_lat_returns_422(client):
    resp = await client.post(
        "/api/v1/route/evaluate",
        json={"waypoints": [{"lat": 999.0, "lon": 76.0}, {"lat": 11.0, "lon": 77.0}]},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_route_evaluate_intersects_mpa_and_has_warnings(client, monkeypatch):
    fake = RouteEvaluationOut(
        route_cost=45.2,
        risk_level="high",
        geofence_violations=[
            {
                "id": "mpa-1",
                "name": "Gulf of Mannar",
                "source": "MoES",
                "version": "1.0",
                "effective_date": "2025-01-01T00:00:00+00:00",
                "geometry": None,
            }
        ],
        hazard_warnings=[
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
    )

    async def fake_evaluate(db, waypoints, vessel_type, max_wave_height):
        return fake

    monkeypatch.setattr("app.services.route_service.evaluate_route", fake_evaluate)

    resp = await client.post(
        "/api/v1/route/evaluate",
        json={
            "waypoints": [{"lat": 10.0, "lon": 76.0}, {"lat": 11.0, "lon": 77.0}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["risk_level"] == "high"
    assert len(body["data"]["geofence_violations"]) == 1
    assert body["data"]["geofence_violations"][0]["name"] == "Gulf of Mannar"
    assert len(body["data"]["hazard_warnings"]) == 1
    assert body["data"]["hazard_warnings"][0]["severity"] == "high"
    assert "request_id" in body["meta"]


async def test_route_evaluate_service_error_returns_500(client, monkeypatch):
    async def fake_evaluate(db, waypoints, vessel_type, max_wave_height):
        raise RuntimeError("route evaluation failed")

    monkeypatch.setattr("app.services.route_service.evaluate_route", fake_evaluate)

    resp = await client.post(
        "/api/v1/route/evaluate",
        json={
            "waypoints": [{"lat": 10.0, "lon": 76.0}, {"lat": 11.0, "lon": 77.0}],
        },
    )
    assert resp.status_code == 500
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0
    assert "request_id" in body["meta"]


async def test_route_evaluate_envelope_contains_meta_fields(client, monkeypatch):
    fake = RouteEvaluationOut(
        route_cost=10.0,
        risk_level="low",
        geofence_violations=[],
        hazard_warnings=[],
    )

    async def fake_evaluate(db, waypoints, vessel_type, max_wave_height):
        return fake

    monkeypatch.setattr("app.services.route_service.evaluate_route", fake_evaluate)

    resp = await client.post(
        "/api/v1/route/evaluate",
        json={
            "waypoints": [{"lat": 10.0, "lon": 76.0}, {"lat": 11.0, "lon": 77.0}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]
    assert body["errors"] == []

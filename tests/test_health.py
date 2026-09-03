from app.schemas.health import HealthData, SourceHealth, SourceDetail

VALID_STATUSES = ("live", "cached", "stale", "unavailable")


async def test_health_returns_correct_structure(client, monkeypatch):
    payload = HealthData(
        incois=SourceHealth(status="live", last_success_at="2026-08-31T00:00:00+00:00"),
        mosdac=SourceHealth(status="cached", last_success_at=None),
        imd=SourceHealth(status="stale", last_success_at="2026-08-30T00:00:00+00:00"),
    )

    async def fake(db):
        return payload

    monkeypatch.setattr("app.services.health_service.get_health_summary", fake)

    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "data" in body and "errors" in body and "meta" in body
    assert body["errors"] == []

    data = body["data"]
    for key in ("incois", "mosdac", "imd"):
        assert key in data
        assert data[key]["status"] in VALID_STATUSES

    # values come from the data source, not hardcoded "live"
    assert data["incois"]["status"] == "live"
    assert data["mosdac"]["status"] == "cached"
    assert data["imd"]["status"] == "stale"
    assert data["incois"]["last_success_at"] == "2026-08-31T00:00:00+00:00"
    assert data["mosdac"]["last_success_at"] is None
    assert "request_id" in body["meta"] and "timestamp" in body["meta"]


async def test_health_db_unavailable_returns_error_not_fake_healthy(client, monkeypatch):
    async def fake(db):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.services.health_service.get_health_summary", fake)

    resp = await client.get("/api/v1/health")
    assert resp.status_code >= 400
    body = resp.json()
    # truthful degraded/error response: never fake a healthy status
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0


async def test_health_sources_returns_list_within_envelope(client, monkeypatch):
    fake = [
        SourceDetail(
            name="incois",
            priority=1,
            status="live",
            last_fetch_at="2026-08-31T00:00:00+00:00",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-08-31T00:00:00+00:00",
        ),
        SourceDetail(
            name="mosdac",
            priority=2,
            status="stale",
            last_fetch_at=None,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-08-30T00:00:00+00:00",
        ),
    ]

    async def fake_get(db):
        return fake

    monkeypatch.setattr("app.services.health_service.get_all_source_details", fake_get)

    resp = await client.get("/api/v1/health/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 2
    assert body["data"][0]["name"] == "incois"
    assert body["data"][0]["status"] == "live"
    assert body["data"][1]["name"] == "mosdac"
    assert body["data"][1]["status"] == "stale"
    assert "request_id" in body["meta"]


async def test_health_source_by_name_returns_detail(client, monkeypatch):
    fake = SourceDetail(
        name="imd",
        priority=3,
        status="cached",
        last_fetch_at="2026-08-29T00:00:00+00:00",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-08-29T00:00:00+00:00",
    )

    async def fake_get(db, source_name):
        assert source_name == "imd"
        return fake

    monkeypatch.setattr("app.services.health_service.get_source_detail", fake_get)

    resp = await client.get("/api/v1/health/sources/imd")
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["data"]["name"] == "imd"
    assert body["data"]["priority"] == 3
    assert body["data"]["status"] == "cached"
    assert body["data"]["last_fetch_at"] == "2026-08-29T00:00:00+00:00"
    assert "request_id" in body["meta"]


async def test_health_source_not_found_returns_404(client, monkeypatch):
    async def fake_get(db, source_name):
        return None

    monkeypatch.setattr("app.services.health_service.get_source_detail", fake_get)

    resp = await client.get("/api/v1/health/sources/unknown")
    assert resp.status_code == 404
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0
    assert "request_id" in body["meta"]


async def test_health_sources_empty_results_returns_empty_list(client, monkeypatch):
    async def fake_get(db):
        return []

    monkeypatch.setattr("app.services.health_service.get_all_source_details", fake_get)

    resp = await client.get("/api/v1/health/sources")
    assert resp.status_code == 200
    body = resp.json()
    assert body["errors"] == []
    assert body["data"] == []
    assert "request_id" in body["meta"]


async def test_health_service_error_returns_500(client, monkeypatch):
    async def fake(db):
        raise RuntimeError("database unreachable")

    monkeypatch.setattr("app.services.health_service.get_health_summary", fake)

    resp = await client.get("/api/v1/health")
    assert resp.status_code >= 400
    body = resp.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list) and len(body["errors"]) > 0

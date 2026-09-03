import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_app_starts():
    assert app is not None


@pytest.mark.asyncio
async def test_ping_returns_200(client: AsyncClient):
    response = await client.get("/ping")
    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "errors" in body
    assert "meta" in body
    assert body["data"] == {"status": "ok"}
    assert body["errors"] == []
    assert "request_id" in body["meta"]
    assert "timestamp" in body["meta"]


@pytest.mark.asyncio
async def test_error_response_has_correct_structure(client: AsyncClient):
    from fastapi import HTTPException
    from app.exceptions import register_exception_handlers

    @app.get("/test-error")
    async def test_error():
        raise HTTPException(status_code=400, detail="Bad request")

    response = await client.get("/test-error")
    assert response.status_code == 400
    body = response.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list)
    assert len(body["errors"]) > 0
    assert isinstance(body["errors"][0], str)
    assert "request_id" in body["meta"]


@pytest.mark.asyncio
async def test_validation_error_does_not_return_nested_objects(client: AsyncClient):
    from pydantic import BaseModel
    from fastapi import APIRouter

    router = APIRouter()

    class TestModel(BaseModel):
        name: str
        age: int

    @router.post("/test-validation")
    async def test_validation(payload: TestModel):
        return {"ok": True}

    app.include_router(router, prefix="/api/v1/test")

    response = await client.post("/api/v1/test/test-validation", json={"name": 123})
    assert response.status_code == 422
    body = response.json()
    assert body["data"] is None
    assert isinstance(body["errors"], list)
    for error in body["errors"]:
        assert isinstance(error, str), f"Error item should be string, got {type(error)}: {error}"


@pytest.mark.asyncio
async def test_cors_headers(client: AsyncClient):
    response = await client.get("/ping", headers={"Origin": "http://localhost:8080"})
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"


@pytest.mark.asyncio
async def test_request_id_header(client: AsyncClient):
    response = await client.get("/ping", headers={"X-Request-ID": "test-req-123"})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == "test-req-123"

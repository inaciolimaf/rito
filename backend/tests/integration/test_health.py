from httpx import AsyncClient
from redis.asyncio import Redis

from app.main import app


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


async def test_health_ready_returns_ok_when_dependencies_up(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"database": "ok", "redis": "ok"}


async def test_health_ready_returns_503_when_redis_down(client: AsyncClient) -> None:
    original_redis = app.state.redis
    app.state.redis = Redis.from_url("redis://localhost:1/0")
    try:
        response = await client.get("/health/ready")
    finally:
        await app.state.redis.aclose()
        app.state.redis = original_redis

    assert response.status_code == 503
    body = response.json()
    assert body["redis"] == "error"
    assert body["database"] == "ok"

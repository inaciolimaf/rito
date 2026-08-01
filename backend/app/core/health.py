from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/health/ready")
async def health_ready(request: Request) -> JSONResponse:
    database_status = "ok"
    redis_status = "ok"

    try:
        async with request.app.state.session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        database_status = "error"

    try:
        await request.app.state.redis.ping()
    except Exception:
        redis_status = "error"

    body = {"database": database_status, "redis": redis_status}
    status_code = 200 if database_status == "ok" and redis_status == "ok" else 503
    return JSONResponse(status_code=status_code, content=body)

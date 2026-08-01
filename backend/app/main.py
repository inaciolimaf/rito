from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.core.config import get_settings
from app.core.db import create_engine, create_session_factory
from app.core.errors import (
    handle_http_exception,
    handle_unhandled_exception,
    handle_validation_error,
)
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.core.redis import create_redis_client


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = create_engine()
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = create_redis_client()

    yield

    await app.state.redis.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Rito", version=__version__, lifespan=lifespan)

    app.add_middleware(RequestIDMiddleware)

    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unhandled_exception)

    app.include_router(health_router)

    return app


app = create_app()

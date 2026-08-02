from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
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
from app.domain.account.router import router as account_router
from app.domain.action_groups.router import action_groups_router, lawsuit_types_router
from app.domain.auth.router import router as auth_router
from app.domain.courts.router import court_systems_router, courts_router
from app.domain.customer_origins.router import router as customer_origins_router
from app.domain.customers.router import customers_router, marital_statuses_router
from app.domain.lawsuits.router import router as lawsuits_router
from app.domain.locations.router import cities_router, states_router
from app.domain.squads.router import router as squads_router
from app.domain.stages.router import stages_router, steps_router
from app.domain.users.router import invitations_router, occupations_router, users_router
from app.integrations.storage.s3 import create_file_storage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = create_engine()
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = create_redis_client()
    app.state.file_storage = create_file_storage()

    yield

    await app.state.redis.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Rito", version=__version__, lifespan=lifespan)

    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIDMiddleware)

    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unhandled_exception)

    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(account_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(occupations_router, prefix="/api/v1")
    app.include_router(invitations_router, prefix="/api/v1")
    app.include_router(squads_router, prefix="/api/v1")
    app.include_router(action_groups_router, prefix="/api/v1")
    app.include_router(lawsuit_types_router, prefix="/api/v1")
    app.include_router(steps_router, prefix="/api/v1")
    app.include_router(stages_router, prefix="/api/v1")
    app.include_router(customer_origins_router, prefix="/api/v1")
    app.include_router(customers_router, prefix="/api/v1")
    app.include_router(marital_statuses_router, prefix="/api/v1")
    app.include_router(states_router, prefix="/api/v1")
    app.include_router(cities_router, prefix="/api/v1")
    app.include_router(courts_router, prefix="/api/v1")
    app.include_router(court_systems_router, prefix="/api/v1")
    app.include_router(lawsuits_router, prefix="/api/v1")

    return app


app = create_app()

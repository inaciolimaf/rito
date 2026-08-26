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
from app.domain.aggregates.router import router as aggregates_router
from app.domain.ai.actions_router import router as ai_actions_router
from app.domain.ai.copilot_router import router as ai_copilot_router
from app.domain.ai.router import router as ai_router
from app.domain.ai.threads_router import router as ai_threads_router
from app.domain.attachments.router import router as attachments_router
from app.domain.auth.router import router as auth_router
from app.domain.bi.router import router as bi_router
from app.domain.comments.router import router as comments_router
from app.domain.courts.router import court_systems_router, courts_router
from app.domain.crm.router import router as crm_router
from app.domain.customer_origins.router import router as customer_origins_router
from app.domain.customers.router import customers_router, marital_statuses_router
from app.domain.documents.router import router as documents_router
from app.domain.dunning.router import router as dunning_router
from app.domain.financial.router import router as financial_router
from app.domain.inbox.router import router as inbox_router
from app.domain.integration_alerts.router import router as integration_alerts_router
from app.domain.integrations.router import router as integrations_router
from app.domain.lawsuits.router import router as lawsuits_router
from app.domain.locations.router import cities_router, states_router
from app.domain.monitored_terms.router import router as monitored_terms_router
from app.domain.notifications.router import router as notifications_router
from app.domain.partnerships.router import lawsuit_sharing_router
from app.domain.partnerships.router import router as partnerships_router
from app.domain.posts.router import router as posts_router
from app.domain.publications.analysis_router import router as publication_analysis_router
from app.domain.publications.router import router as publications_router
from app.domain.reports.router import router as reports_router
from app.domain.schedule.router import ical_router
from app.domain.schedule.router import router as schedule_router
from app.domain.squads.router import router as squads_router
from app.domain.stages.router import stages_router, steps_router
from app.domain.task_types.router import router as task_types_router
from app.domain.taskscore.router import goals_router, taskscore_router
from app.domain.templates.router import router as templates_router
from app.domain.users.router import invitations_router, occupations_router, users_router
from app.domain.workflows.router import router as workflows_router
from app.integrations.messaging.registry import create_document_mailer, create_messaging_channels
from app.integrations.openrouter.factory import create_llm_provider
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
    app.state.messaging_channels = create_messaging_channels()
    app.state.document_mailer = create_document_mailer()
    # Spec 081: um provider para o app inteiro — nenhuma rota monta client de LLM.
    app.state.llm_provider = create_llm_provider(redis=app.state.redis)

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
    app.include_router(lawsuit_sharing_router, prefix="/api/v1")
    app.include_router(partnerships_router, prefix="/api/v1")
    app.include_router(crm_router, prefix="/api/v1")
    app.include_router(task_types_router, prefix="/api/v1")
    app.include_router(financial_router, prefix="/api/v1")
    app.include_router(dunning_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    app.include_router(templates_router, prefix="/api/v1")
    # inbox ANTES de posts: /posts/bulk/* perderia para /posts/{post_id}/* no match
    # por ordem de registro ("bulk" não parseia como uuid → 422).
    app.include_router(inbox_router, prefix="/api/v1")
    app.include_router(posts_router, prefix="/api/v1")
    app.include_router(comments_router, prefix="/api/v1")
    app.include_router(attachments_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(schedule_router, prefix="/api/v1")
    # Feed iCal público por token (spec 037 §5) — fora de /api/v1 por decisão da spec.
    app.include_router(ical_router)
    app.include_router(workflows_router, prefix="/api/v1")
    app.include_router(goals_router, prefix="/api/v1")
    app.include_router(taskscore_router, prefix="/api/v1")
    # Análise por IA antes do router de intimações: `/publications/analysis/estimate`
    # perderia para `/publications/{publication_id}` por ordem de registro.
    app.include_router(publication_analysis_router, prefix="/api/v1")
    app.include_router(publications_router, prefix="/api/v1")
    app.include_router(monitored_terms_router, prefix="/api/v1")
    app.include_router(integration_alerts_router, prefix="/api/v1")
    app.include_router(integrations_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    app.include_router(bi_router, prefix="/api/v1")
    app.include_router(aggregates_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(ai_actions_router, prefix="/api/v1")
    app.include_router(ai_copilot_router, prefix="/api/v1")
    app.include_router(ai_threads_router, prefix="/api/v1")

    return app


app = create_app()

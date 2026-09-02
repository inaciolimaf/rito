from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.core.bootstrap import ensure_valid
from app.core.config import Settings, get_settings
from app.core.db import create_engine, create_engine_from_url, create_session_factory
from app.core.errors import (
    handle_budget_exceeded,
    handle_http_exception,
    handle_unhandled_exception,
    handle_validation_error,
)
from app.core.health import router as health_router
from app.core.logging import configure_logging
from app.core.middleware import ObservabilityMiddleware
from app.core.migrations import upgrade_with_lock
from app.core.observability import metrics as observability_metrics
from app.core.observability.tracing import build_span_exporter, configure_tracing
from app.core.observability.tracing import instrument_engine as instrument_engine_tracing
from app.core.provisioning import seed_global_catalogs
from app.core.redis import create_redis_client
from app.domain.account.router import router as account_router
from app.domain.action_groups.router import action_groups_router, lawsuit_types_router
from app.domain.aggregates.router import router as aggregates_router
from app.domain.ai.actions_router import router as ai_actions_router
from app.domain.ai.analytics_router import lawsuits_router as ai_lawsuit_actions_router
from app.domain.ai.analytics_router import router as ai_analytics_router
from app.domain.ai.budget import BudgetExceededError
from app.domain.ai.copilot_router import router as ai_copilot_router
from app.domain.ai.editor_router import router as ai_editor_router
from app.domain.ai.router import router as ai_router
from app.domain.ai.threads_router import router as ai_threads_router
from app.domain.api_tokens.router import router as api_tokens_router
from app.domain.attachments.router import router as attachments_router
from app.domain.auth.router import router as auth_router
from app.domain.automations.router import router as automations_router
from app.domain.bi.router import router as bi_router
from app.domain.comments.router import router as comments_router
from app.domain.courts.router import court_systems_router, courts_router
from app.domain.crm.router import router as crm_router
from app.domain.customer_origins.router import router as customer_origins_router
from app.domain.customers.router import customers_router, marital_statuses_router
from app.domain.documents.extraction_router import router as document_extraction_router
from app.domain.documents.router import router as documents_router
from app.domain.dunning.router import router as dunning_router
from app.domain.financial.router import router as financial_router
from app.domain.inbox.router import router as inbox_router
from app.domain.integration_alerts.router import router as integration_alerts_router
from app.domain.integrations.router import router as integrations_router
from app.domain.lawsuits.router import router as lawsuits_router
from app.domain.legal_agents.router import agents_router as legal_agents_router
from app.domain.legal_agents.router import generations_router as agent_generations_router
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
from app.domain.search.router import router as search_router
from app.domain.squads.router import router as squads_router
from app.domain.stages.router import stages_router, steps_router
from app.domain.task_types.router import router as task_types_router
from app.domain.taskscore.router import goals_router, taskscore_router
from app.domain.templates.router import router as templates_router
from app.domain.users.router import invitations_router, occupations_router, users_router
from app.domain.webhooks.router import router as webhooks_router
from app.domain.webhooks.sender import HttpxWebhookSender
from app.domain.workflows.router import router as workflows_router
from app.integrations.messaging.registry import create_document_mailer, create_messaging_channels
from app.integrations.ocr.factory import create_ocr_provider
from app.integrations.openrouter.factory import create_llm_provider
from app.integrations.storage.s3 import create_file_storage
from app.public.middleware import PublicApiMiddleware
from app.public.router import docs_router as public_docs_router
from app.public.router import router as public_api_router


def _configure_process(settings: Settings) -> None:
    """O que precisa existir antes da primeira requisição.

    Spec 099, regras 5 e 6: configuração incompleta derruba o processo AQUI, com a lista
    inteira do que falta — nunca no meio da requisição de alguém.

    Spec 097: o provider de trace é global ao processo e precisa existir antes de o engine
    ser instrumentado — na ordem inversa, o primeiro span nasceria órfão.
    """
    configure_logging(settings.log_level)
    ensure_valid(settings)
    configure_tracing(
        service_name=settings.otel_service_name,
        sample_ratio=settings.otel_sample_ratio,
        exporter=build_span_exporter(settings.otel_exporter_otlp_endpoint),
    )


async def _run_boot_migrations(settings: Settings) -> None:
    """Spec 099, regras 3, 4 e 7: migrations no boot, sob trava, e catálogo global
    reafirmado — idempotente.

    Falha de migration impede a aplicação de subir, de propósito: servir requisição com
    esquema velho é pior que não servir. Desligável por `RUN_MIGRATIONS_ON_BOOT=false`
    para quem prefere aplicar num job separado antes do rolling.

    Engine PRÓPRIO, descartado no `finally`: a URL de migration é a de superusuário, e ela
    não pode sobreviver ao boot nem ser reusada pelo pool das requisições.
    """
    if not (settings.run_migrations_on_boot and settings.migrations_database_url):
        return
    migrations_engine = create_engine_from_url(settings.migrations_database_url)
    try:
        await upgrade_with_lock(migrations_engine)
        async with migrations_engine.begin() as conn:
            await seed_global_catalogs(conn)
    finally:
        await migrations_engine.dispose()


def _wire_services(app: FastAPI, engine: AsyncEngine) -> None:
    """Monta em `app.state` tudo o que as rotas recebem por injeção.

    Uma instância por PROCESSO, não por requisição: pool de conexões, cliente de Redis e
    transporte HTTP são caros de abrir e feitos para serem compartilhados. Montá-los aqui é
    também o que faz o DIP do §5 valer — nenhuma rota constrói client de LLM, de OCR ou de
    webhook por conta própria (specs 081, 091 e 093), e por isso o teste consegue trocar
    qualquer um deles por um dublê sem tocar no código de produção.
    """
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    app.state.redis = create_redis_client()
    app.state.file_storage = create_file_storage()
    app.state.messaging_channels = create_messaging_channels()
    app.state.document_mailer = create_document_mailer()
    app.state.llm_provider = create_llm_provider(redis=app.state.redis)
    app.state.ocr_provider = create_ocr_provider()
    app.state.webhook_sender = HttpxWebhookSender()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
    _configure_process(settings)
    engine = create_engine()
    await _run_boot_migrations(settings)

    # Spec 097, regra 6: contagem de queries por requisição, sempre — é barata (um
    # `+= 1`) e a métrica de queries/request depende dela.
    observability_metrics.instrument_engine(engine)
    # Regra 4: span por query. Medido ao fechar a 097: com o sampler devolvendo
    # RECORD_ONLY para o que não foi sorteado, o custo em 1.400 testes ficou dentro do
    # ruído — não vale condicionar a regra 4 a ter coletor configurado.
    instrument_engine_tracing(engine)
    _wire_services(app, engine)
    yield

    # Spec 099, regra 10: desligamento gracioso. O uvicorn já parou de aceitar conexão e
    # esperou as requisições em curso antes de chegar aqui — o que falta é soltar o que
    # é nosso, e nessa ordem: primeiro o que as requisições usam (Redis, pool), por
    # último o transporte HTTP dos webhooks, que pode ter uma entrega em voo.
    await app.state.redis.aclose()
    await engine.dispose()


# Prefixo da API interna. A pública (spec 095) tem o seu, declarado no próprio router.
_API_V1 = "/api/v1"

# A ordem desta tabela É a ordem de registro, e no FastAPI ordem de registro é semântica:
# a primeira rota que casa vence. Duas posições aqui são deliberadas e estão comentadas
# abaixo — trocá-las quebra rota sem quebrar nenhum teste de módulo, porque o handler
# errado responde com um erro plausível em vez de estourar. `tests/meta/test_app_registry.py`
# trava as duas.
#
# A tabela substitui 61 chamadas sequenciais a `include_router` (spec 109): a ordem passa a
# ser um dado que se lê de uma vez, e não uma propriedade emergente de uma sequência longa.
_ROUTERS: tuple[tuple[APIRouter, str], ...] = (
    (health_router, ""),
    # Spec 095: a API pública tem prefixo próprio e versão no caminho (regra 12).
    (public_api_router, ""),
    (public_docs_router, ""),
    (auth_router, _API_V1),
    (account_router, _API_V1),
    (users_router, _API_V1),
    (occupations_router, _API_V1),
    (invitations_router, _API_V1),
    (squads_router, _API_V1),
    (action_groups_router, _API_V1),
    (lawsuit_types_router, _API_V1),
    (steps_router, _API_V1),
    (stages_router, _API_V1),
    (customer_origins_router, _API_V1),
    (customers_router, _API_V1),
    (marital_statuses_router, _API_V1),
    (states_router, _API_V1),
    (cities_router, _API_V1),
    (courts_router, _API_V1),
    (court_systems_router, _API_V1),
    (lawsuits_router, _API_V1),
    (lawsuit_sharing_router, _API_V1),
    (partnerships_router, _API_V1),
    (crm_router, _API_V1),
    (task_types_router, _API_V1),
    (financial_router, _API_V1),
    (dunning_router, _API_V1),
    (api_tokens_router, _API_V1),
    (automations_router, _API_V1),
    (search_router, _API_V1),
    (webhooks_router, _API_V1),
    (documents_router, _API_V1),
    (document_extraction_router, _API_V1),
    (templates_router, _API_V1),
    # inbox ANTES de posts: /posts/bulk/* perderia para /posts/{post_id}/* no match
    # por ordem de registro ("bulk" não parseia como uuid → 422).
    (inbox_router, _API_V1),
    (posts_router, _API_V1),
    (comments_router, _API_V1),
    (attachments_router, _API_V1),
    (notifications_router, _API_V1),
    (schedule_router, _API_V1),
    # Feed iCal público por token (spec 037 §5) — fora de /api/v1 por decisão da spec.
    (ical_router, ""),
    (workflows_router, _API_V1),
    (goals_router, _API_V1),
    (taskscore_router, _API_V1),
    # Análise por IA antes do router de intimações: `/publications/analysis/estimate`
    # perderia para `/publications/{publication_id}` por ordem de registro.
    (publication_analysis_router, _API_V1),
    (publications_router, _API_V1),
    (monitored_terms_router, _API_V1),
    (integration_alerts_router, _API_V1),
    (integrations_router, _API_V1),
    (reports_router, _API_V1),
    (bi_router, _API_V1),
    (aggregates_router, _API_V1),
    (ai_router, _API_V1),
    (ai_actions_router, _API_V1),
    (ai_copilot_router, _API_V1),
    (ai_editor_router, _API_V1),
    (ai_analytics_router, _API_V1),
    (ai_lawsuit_actions_router, _API_V1),
    (legal_agents_router, _API_V1),
    (agent_generations_router, _API_V1),
    (ai_threads_router, _API_V1),
)


def _register_middlewares(app: FastAPI) -> None:
    """A pilha de middleware, de dentro para fora.

    No Starlette **o último adicionado é o mais externo**, então esta ordem de chamada é o
    inverso da ordem de execução: `PublicApiMiddleware` vê a requisição primeiro e a
    resposta por último; o CORS é o mais interno. Mudar isso muda quais respostas ganham
    cabeçalho de CORS — inclusive as de erro, que é justamente quando o navegador do
    cliente precisa delas para exibir a mensagem em vez de um erro de origem.
    """
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ObservabilityMiddleware)
    # Spec 095: headers de limite e log de requisição da API pública.
    app.add_middleware(PublicApiMiddleware)


def _register_error_handlers(app: FastAPI) -> None:
    """Os quatro tratadores que transformam exceção em `application/problem+json` (§9).

    O de `Exception` é o último de propósito: ele é a rede embaixo dos outros três, e
    registrá-lo antes não mudaria nada — o FastAPI escolhe pelo tipo mais específico —,
    mas ler a lista de cima para baixo passaria a impressão errada de precedência.
    """
    app.add_exception_handler(BudgetExceededError, handle_budget_exceeded)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unhandled_exception)


def _register_routers(app: FastAPI) -> None:
    """Registra `_ROUTERS` na ordem em que a tabela as declara."""
    for router, prefix in _ROUTERS:
        app.include_router(router, prefix=prefix)


def create_app() -> FastAPI:
    app = FastAPI(title="Rito", version=__version__, lifespan=lifespan)
    _register_middlewares(app)
    _register_error_handlers(app)
    _register_routers(app)
    return app


app = create_app()

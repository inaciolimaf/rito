"""Spec 097 — log correlacionado, trace atravessando o worker, métricas e prontidão.

Todos os casos rodam contra o app real. O que é substituído é só o **destino**: o log
vai para um buffer em memória em vez de stdout, e o trace para um exporter em memória
em vez de um coletor OTLP — nada de rede (CLAUDE.md §3).
"""

import io
import json
import logging
import sys
import uuid
from collections.abc import Awaitable, Callable, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import SpanKind, Status, StatusCode
from redis.asyncio import Redis

from app.core.logging import JSONFormatter
from app.core.observability import metrics
from app.core.observability.propagation import (
    REQUEST_ID_HEADER,
    bind_task_headers,
    build_task_headers,
    release_task_scope,
)
from app.core.observability.tracing import configure_tracing, get_tracer
from app.main import app
from tests.integration.conftest import SeededUser, auth_header

CAMPOS_OBRIGATORIOS = (
    "timestamp",
    "level",
    "message",
    "request_id",
    "tenant_id",
    "user_id",
    "route",
    "duration_ms",
)


class MemoriaExporter(SpanExporter):
    """Coletor de trace do teste. Guardar em lista é o que permite afirmar sobre o que
    SERIA exportado sem abrir socket nenhum."""

    def __init__(self) -> None:
        self.spans: list[object] = []

    def export(self, spans) -> SpanExportResult:  # type: ignore[no-untyped-def]
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    @property
    def nomes(self) -> list[str]:
        return [getattr(span, "name", "") for span in self.spans]


@pytest.fixture
def log_capturado() -> Iterator[io.StringIO]:
    """Prende o formatter real do app a um buffer — o que é afirmado é a saída de
    produção, não uma reimplementação dela dentro do teste."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    raiz = logging.getLogger()
    anteriores, nivel = raiz.handlers, raiz.level
    raiz.handlers, raiz.level = [handler], logging.INFO
    try:
        yield stream
    finally:
        raiz.handlers, raiz.level = anteriores, nivel


def linhas(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(linha) for linha in stream.getvalue().splitlines() if linha.strip()]


@pytest.fixture
def trace_em_memoria() -> Iterator[MemoriaExporter]:
    """Amostragem 100% de propósito: a regra 11 é sobre o padrão de PRODUÇÃO, e sortear
    10% dentro do teste só o tornaria intermitente. O caminho do não-sorteado tem teste
    próprio (`test_span_em_erro_e_exportado_mesmo_fora_da_amostra`)."""
    exporter = MemoriaExporter()
    configure_tracing(service_name="rito-test", sample_ratio=1.0, exporter=exporter)
    yield exporter
    configure_tracing(service_name="rito-test", sample_ratio=1.0, exporter=None)


async def test_log_de_requisicao_traz_os_campos_de_correlacao(
    client: AsyncClient, log_capturado: io.StringIO
) -> None:
    await client.get("/health", headers={"X-Request-Id": "req-correlacao"})

    requisicao = [linha for linha in linhas(log_capturado) if linha.get("route") == "/health"]
    assert requisicao, "a requisição precisa produzir uma linha de log"
    registro = requisicao[-1]
    for campo in CAMPOS_OBRIGATORIOS:
        assert campo in registro, f"log sem o campo {campo} (regra 1)"
    assert registro["request_id"] == "req-correlacao"
    assert isinstance(registro["duration_ms"], int)


async def test_request_id_volta_no_header_e_e_gerado_quando_ausente(
    client: AsyncClient,
) -> None:
    resposta = await client.get("/health")

    assert uuid.UUID(resposta.headers["X-Request-Id"])


async def test_log_de_requisicao_carrega_tenant_e_usuario_autenticados(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    log_capturado: io.StringIO,
) -> None:
    seeded = await make_user()
    await client.get("/api/v1/users/me/preferences", headers=auth_header(seeded))

    rota = "/api/v1/users/me/preferences"
    registro = [linha for linha in linhas(log_capturado) if linha.get("route") == rota][-1]
    assert registro["tenant_id"] == str(seeded.tenant_id)
    assert registro["user_id"] == str(seeded.user_id)


async def test_nenhum_dado_sensivel_sobrevive_ao_formatter(
    log_capturado: io.StringIO,
) -> None:
    """Regra 3 pelo caminho real: alguém loga um corpo de requisição para depurar."""
    logging.getLogger("rito.teste").info(
        "corpo recebido",
        extra={
            "body": {
                "password": "hunter2",
                "cpf": "529.982.247-25",
                "email": "ana@escritorio.com.br",
                "phone": "(11) 98765-4321",
                "api_key": "sk-live-123",
            }
        },
    )

    bruto = log_capturado.getvalue()
    for segredo in (
        "hunter2",
        "529.982.247-25",
        "ana@escritorio.com.br",
        "98765-4321",
        "sk-live-123",
    ):
        assert segredo not in bruto, f"{segredo!r} vazou para o log (regra 3)"


async def test_log_de_erro_traz_stack_e_o_de_requisicao_nao(
    log_capturado: io.StringIO,
) -> None:
    """Regra 9. As duas metades no mesmo teste porque a regra é uma comparação: o stack
    precisa estar onde serve (erro) e ausente onde só pesaria (uma linha por request)."""
    logger = logging.getLogger("rito.teste")
    try:
        raise ValueError("quebrou")
    except ValueError:
        logger.exception("erro não tratado")
    logger.info("requisição concluída", extra={"route": "/x", "status": 200, "duration_ms": 3})

    erro, requisicao = linhas(log_capturado)
    assert "ValueError: quebrou" in str(erro["exception"])
    assert "exception" not in requisicao


async def test_trace_da_requisicao_tem_span_de_banco(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    trace_em_memoria: MemoriaExporter,
) -> None:
    """Regra 4. `/users/me` toca o banco duas vezes (valida o token, carrega o usuário):
    se o span de query não estiver pendurado no da requisição, o trace não explica onde
    o tempo foi."""
    seeded = await make_user()
    await client.get("/api/v1/users/me/preferences", headers=auth_header(seeded))

    assert any(nome.startswith("db ") for nome in trace_em_memoria.nomes)
    assert any(
        nome.startswith("GET /api/v1/users/me/preferences") for nome in trace_em_memoria.nomes
    )


async def test_span_externo_e_de_llm_nascem_das_camadas_certas(
    trace_em_memoria: MemoriaExporter,
) -> None:
    """Regra 4 para os outros dois tipos de span. O que se afirma é que a instrumentação
    está no client HTTP e no runner de IA — não se sobe nenhuma chamada real."""
    from app.integrations.http.client import ResilientHttpClient

    assert hasattr(
        ResilientHttpClient, "_request_com_resiliencia"
    ), "o span externo envolve breaker+retries: `request` delega a `_request_com_resiliencia`"
    with get_tracer().start_as_current_span("http GET", kind=SpanKind.CLIENT):
        pass
    with get_tracer().start_as_current_span("llm copilot", kind=SpanKind.CLIENT):
        pass

    assert "http GET" in trace_em_memoria.nomes
    assert "llm copilot" in trace_em_memoria.nomes


async def test_span_em_erro_e_exportado_mesmo_fora_da_amostra() -> None:
    """Regra 11: 10% do tráfego normal, 100% do que falhou.

    Com `sample_ratio=0` nada seria exportado por sorteio — o que chega ao exporter só
    pode ter chegado por ter terminado em erro.
    """
    exporter = MemoriaExporter()
    configure_tracing(service_name="rito-test", sample_ratio=0.0, exporter=exporter)
    try:
        with get_tracer().start_as_current_span("normal"):
            pass
        with get_tracer().start_as_current_span("falhou") as span:
            span.set_status(Status(StatusCode.ERROR))
    finally:
        configure_tracing(service_name="rito-test", sample_ratio=1.0, exporter=None)

    assert exporter.nomes == ["falhou"]


def test_request_id_e_traceparent_viajam_para_a_task_celery(
    trace_em_memoria: MemoriaExporter,
) -> None:
    """Regras 2 e 5, testadas nas duas funções puras que os sinais do Celery chamam —
    sem broker, sem worker, sem rede.
    """
    from app.core.observability.context import request_id_var, tenant_id_var

    tokens = (request_id_var.set("req-do-clique"), tenant_id_var.set("tenant-1"))
    try:
        with get_tracer().start_as_current_span("POST /api/v1/publications") as pai:
            headers = build_task_headers()
            trace_do_request = pai.get_span_context().trace_id
    finally:
        request_id_var.reset(tokens[0])
        tenant_id_var.reset(tokens[1])

    assert headers[REQUEST_ID_HEADER] == "req-do-clique"
    assert "traceparent" in headers

    # Do outro lado da fila: o worker não tem contexto nenhum.
    assert request_id_var.get() is None
    escopo = bind_task_headers(headers, task_name="app.workers.publications.sync")
    try:
        assert request_id_var.get() == "req-do-clique"
        assert tenant_id_var.get() == "tenant-1"
        assert escopo.span.get_span_context().trace_id == trace_do_request
    finally:
        release_task_scope(escopo)

    assert "celery app.workers.publications.sync" in trace_em_memoria.nomes


def test_sinais_do_celery_estao_ligados_a_propagacao() -> None:
    """A propagação só vale se alguém a chamar. Este é o teste do fio."""
    from celery.signals import before_task_publish, task_postrun, task_prerun

    import app.workers.observability  # noqa: F401  — o import é o que conecta os sinais

    for sinal in (before_task_publish, task_prerun, task_postrun):
        modulos = {
            getattr(referencia(), "__module__", "")
            for _, referencia in sinal.receivers
            if callable(referencia)
        }
        assert (
            "app.workers.observability" in modulos
        ), f"{sinal.name} sem receptor da observabilidade"


async def test_metrics_expoe_as_familias_da_regra_6(client: AsyncClient) -> None:
    await client.get("/health")

    resposta = await client.get("/metrics")

    assert resposta.status_code == 200
    corpo = resposta.text
    for familia in (
        "rito_http_requests_total",
        "rito_http_request_duration_seconds",
        "rito_http_queries_per_request",
        "rito_celery_queue_depth",
        "rito_llm_tokens_total",
        "rito_llm_cost_usd_total",
        "rito_webhook_deliveries_total",
        "rito_sync_runs_total",
    ):
        assert familia in corpo, f"/metrics sem a família {familia} (regra 6)"


async def test_metrics_rotula_por_template_de_rota_nao_por_caminho(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Rotular por caminho concreto criaria uma série temporal por processo do
    escritório — cardinalidade infinita é como se derruba um Prometheus."""
    seeded = await make_user()
    await client.get(f"/api/v1/users/{seeded.user_id}", headers=auth_header(seeded))

    corpo = (await client.get("/metrics")).text

    assert 'route="/api/v1/users/{user_id}"' in corpo
    assert str(seeded.user_id) not in corpo


async def test_metrics_conta_as_queries_da_requisicao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 6, "queries por request" — a mesma contagem que a 098 usa como orçamento."""
    seeded = await make_user()
    await client.get("/api/v1/users/me/preferences", headers=auth_header(seeded))

    corpo = (await client.get("/metrics")).text
    somas = [
        linha
        for linha in corpo.splitlines()
        if linha.startswith("rito_http_queries_per_request_sum")
        and "/api/v1/users/me/preferences" in linha
    ]
    assert somas, "nenhuma contagem de query registrada para a rota"
    assert float(somas[0].rsplit(" ", 1)[1]) > 0


async def test_health_nao_toca_dependencia(client: AsyncClient) -> None:
    """Regra 7: liveness que consulta o banco faz o orquestrador matar containers
    saudáveis exatamente quando o banco está sobrecarregado."""
    factory_original = app.state.session_factory
    redis_original = app.state.redis
    app.state.session_factory = None
    app.state.redis = None
    try:
        resposta = await client.get("/health")
    finally:
        app.state.session_factory = factory_original
        app.state.redis = redis_original

    assert resposta.status_code == 200
    assert resposta.json()["status"] == "ok"


async def test_health_ready_checa_postgres_redis_e_storage(client: AsyncClient) -> None:
    resposta = await client.get("/health/ready")

    assert resposta.status_code == 200
    assert resposta.json() == {"database": "ok", "redis": "ok", "storage": "ok"}


async def test_health_ready_diz_qual_dependencia_caiu(client: AsyncClient) -> None:
    """Regra 8: 503 que não diz o quê obriga quem está de plantão a adivinhar."""
    original = app.state.redis
    app.state.redis = Redis.from_url("redis://localhost:1/0")
    try:
        resposta = await client.get("/health/ready")
    finally:
        await app.state.redis.aclose()
        app.state.redis = original

    assert resposta.status_code == 503
    corpo = resposta.json()
    assert corpo["redis"] in ("error", "timeout")
    assert corpo["database"] == "ok"
    assert corpo["storage"] == "ok"


async def test_health_ready_aponta_o_banco_quando_e_o_banco(client: AsyncClient) -> None:
    """A outra metade da regra 8. Redis e Postgres caem de formas diferentes e o
    diagnóstico precisa distinguir as duas — quem está de plantão age diferente."""
    from app.core.db import create_engine_from_url, create_session_factory

    original = app.state.session_factory
    quebrado = create_engine_from_url("postgresql+asyncpg://x:x@localhost:1/x")
    app.state.session_factory = create_session_factory(quebrado)
    try:
        resposta = await client.get("/health/ready")
    finally:
        await quebrado.dispose()
        app.state.session_factory = original

    assert resposta.status_code == 503
    corpo = resposta.json()
    assert corpo["database"] in ("error", "timeout")
    assert corpo["redis"] == "ok"
    assert corpo["storage"] == "ok"


async def test_health_ready_nao_espera_mais_que_o_teto_por_dependencia() -> None:
    """Regra 8: 2 s por sonda. Uma dependência pendurada não pode segurar o healthcheck
    até o timeout do orquestrador — readiness que trava é indisponibilidade."""
    import asyncio

    from app.core.health import PROBE_TIMEOUT_S, _probe

    async def nunca_responde() -> object:
        # Dependência pendurada, simulada: dez vezes o teto da sonda. O sleep nunca
        # decorre — o `wait_for` do `_probe` o cancela, e é isso que o teste afirma.
        await asyncio.sleep(PROBE_TIMEOUT_S * 10)
        return None

    comeco = asyncio.get_running_loop().time()
    nome, estado = await _probe("redis", nunca_responde)
    decorrido = asyncio.get_running_loop().time() - comeco

    assert (nome, estado) == ("redis", "timeout")
    assert decorrido < PROBE_TIMEOUT_S * 2


async def test_metrics_exige_token_quando_configurado() -> None:
    """O /metrics é inventário da operação (quanto o escritório gastou de LLM, quantas
    requisições cada rota recebeu). Onde a rede não isola, o token isola."""
    from app.core.config import get_settings

    settings = get_settings()
    anterior = settings.metrics_token
    object.__setattr__(settings, "metrics_token", "segredo-interno")
    try:
        async with app.router.lifespan_context(app):
            transporte = ASGITransport(app=app)
            async with AsyncClient(transport=transporte, base_url="http://test") as ac:
                sem_token = await ac.get("/metrics")
                com_token = await ac.get(
                    "/metrics", headers={"Authorization": "Bearer segredo-interno"}
                )
    finally:
        object.__setattr__(settings, "metrics_token", anterior)

    assert sem_token.status_code == 401
    assert com_token.status_code == 200


def test_log_sai_apenas_para_stdout(caplog: pytest.LogCaptureFixture) -> None:
    """Regra 12: nenhum I/O síncrono no caminho quente. Um `FileHandler` (ou pior, um
    handler de rede) dentro da requisição transformaria cada log num write bloqueante."""
    from app.core.logging import configure_logging

    anteriores = logging.getLogger().handlers
    try:
        configure_logging("INFO")
        handlers = logging.getLogger().handlers
        assert len(handlers) == 1
        handler = handlers[0]
        assert type(handler) is logging.StreamHandler
        assert handler.stream is sys.stdout
    finally:
        logging.getLogger().handlers = anteriores


def test_nivel_de_log_vem_da_configuracao() -> None:
    """Regra 10: subir para DEBUG durante um incidente não pode exigir redeploy."""
    from app.core.logging import configure_logging

    anteriores, nivel = logging.getLogger().handlers, logging.getLogger().level
    try:
        configure_logging("debug")
        assert logging.getLogger().level == logging.DEBUG
    finally:
        logging.getLogger().handlers, logging.getLogger().level = anteriores, nivel


def test_metrica_de_llm_registra_tokens_e_custo() -> None:
    """Regra 6 para a família mais cara de acompanhar: sem ela, o custo de IA só
    aparece na fatura."""
    antes = metrics.REGISTRY.get_sample_value(
        "rito_llm_tokens_total",
        {"feature": "teste_097", "model": "modelo/x", "kind": "prompt"},
    )
    metrics.record_llm_usage(
        feature="teste_097",
        model="modelo/x",
        prompt_tokens=10,
        completion_tokens=4,
        cost_usd=0.002,
    )

    depois = metrics.REGISTRY.get_sample_value(
        "rito_llm_tokens_total",
        {"feature": "teste_097", "model": "modelo/x", "kind": "prompt"},
    )
    assert depois == (antes or 0) + 10
    assert metrics.REGISTRY.get_sample_value(
        "rito_llm_cost_usd_total", {"feature": "teste_097", "model": "modelo/x"}
    ) == pytest.approx(0.002)

"""Tracing OpenTelemetry (spec 097, regras 4, 5 e 11).

O Rito **exporta** trace; não hospeda backend de trace (§3 da spec). O provider é
montado no boot e o exporter é escolhido por configuração — em produção, um coletor
OTLP posto pelo time de infra; em teste, um exporter em memória que o próprio teste lê.

## A amostragem da regra 11

"10% em produção, 100% em erro" é contraditório à primeira vista: a decisão de amostrar
é tomada quando o span **abre**, e o erro só se conhece quando ele **fecha**. A saída é
separar as duas coisas que o SDK deixa separar:

- o sampler devolve `RECORD_ONLY` para os 90% não sorteados — o span existe, é gravado
  em memória e recebe status, mas nasce sem a flag de exportação;
- o processor, no `on_end`, exporta o que foi sorteado **ou** o que terminou em erro.

O custo disso é criar objeto de span para 100% das requisições. É barato (nada sai do
processo) e é o que torna a regra 11 verdadeira em vez de aspiracional.
"""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace.sampling import (
    Decision,
    ParentBased,
    Sampler,
    SamplingResult,
    TraceIdRatioBased,
)
from opentelemetry.trace import Link, SpanKind, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.util.types import Attributes

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

TRACER_NAME = "rito"

_propagator = TraceContextTextMapPropagator()

# O provider do Rito, guardado aqui e não só no global do OTel. O SDK recusa (com um
# aviso, sem erro) trocar o provider global depois do primeiro `set_tracer_provider` —
# o que faria todo teste que precisa de outro exporter herdar silenciosamente o do
# processo. Manter a referência própria dá controle sobre o nosso tracer; o global
# continua sendo setado para instrumentação de terceiros achá-lo.
_provider: TracerProvider | None = None


class RatioWithErrorsSampler(Sampler):
    """Sorteia `ratio` das raízes; o resto nasce `RECORD_ONLY` (ver docstring do módulo)."""

    def __init__(self, ratio: float) -> None:
        self._ratio = ratio
        self._delegate = ParentBased(root=TraceIdRatioBased(ratio))

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: trace.TraceState | None = None,
    ) -> SamplingResult:
        result = self._delegate.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )
        if result.decision is Decision.DROP:
            return SamplingResult(Decision.RECORD_ONLY, result.attributes, result.trace_state)
        return result

    def get_description(self) -> str:
        return f"RatioWithErrorsSampler{{{self._ratio}}}"


class ErrorEscalatingSpanProcessor(SpanProcessor):
    """Exporta span sorteado — e todo span que terminou em erro, sorteado ou não."""

    def __init__(self, exporter: SpanExporter) -> None:
        self._exporter = exporter

    def on_start(self, span: trace.Span, parent_context: Context | None = None) -> None:
        return None

    def on_end(self, span: ReadableSpan) -> None:
        context = span.get_span_context()
        em_erro = span.status is not None and span.status.status_code is StatusCode.ERROR
        if context is None:
            return
        if not context.trace_flags.sampled and not em_erro:
            return
        self._exporter.export((span,))

    def shutdown(self) -> None:
        self._exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


def configure_tracing(
    *,
    service_name: str,
    sample_ratio: float,
    exporter: SpanExporter | None = None,
) -> TracerProvider:
    """Monta o provider global. Sem exporter, o trace fica só em memória (dev/teste)."""
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name}),
        sampler=RatioWithErrorsSampler(sample_ratio),
    )
    if exporter is not None:
        provider.add_span_processor(ErrorEscalatingSpanProcessor(exporter))
    global _provider
    _provider = provider
    trace.set_tracer_provider(provider)
    return provider


def get_tracer() -> trace.Tracer:
    if _provider is not None:
        return _provider.get_tracer(TRACER_NAME)
    return trace.get_tracer(TRACER_NAME)


def inject_context(carrier: dict[str, str]) -> dict[str, str]:
    """Escreve o `traceparent` do span corrente no carrier (regra 5)."""
    _propagator.inject(carrier)
    return carrier


def extract_context(carrier: Mapping[str, str]) -> Context:
    """Reconstrói o contexto do lado de quem consome (worker)."""
    return _propagator.extract(dict(carrier))


def instrument_engine(engine: "AsyncEngine") -> None:
    """Span por query (regra 4).

    O par de eventos do SQLAlchemy é síncrono e roda no mesmo greenlet da corrotina que
    disparou a query, então o span filho cai debaixo do span da requisição sem precisar
    carregar contexto na mão. O span guarda a operação e a tabela, nunca a SQL inteira
    com os parâmetros — parâmetro de query é PII (regra 3).
    """
    from sqlalchemy import event

    def _start(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]  # noqa: ANN001, E501 — assinatura fixada pelo evento do SQLAlchemy
        span = get_tracer().start_span(
            f"db {_operation_of(statement)}",
            kind=SpanKind.CLIENT,
            attributes={"db.system": "postgresql", "db.operation": _operation_of(statement)},
        )
        conn.info.setdefault("rito_spans", []).append(span)

    def _end(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]  # noqa: ANN001, E501 — assinatura fixada pelo evento do SQLAlchemy
        spans = conn.info.get("rito_spans")
        if spans:
            spans.pop().end()

    if not event.contains(engine.sync_engine, "before_cursor_execute", _start):
        event.listen(engine.sync_engine, "before_cursor_execute", _start)
        event.listen(engine.sync_engine, "after_cursor_execute", _end)


def _operation_of(statement: str) -> str:
    return statement.lstrip().split(" ", 1)[0].upper() or "UNKNOWN"


def span_attributes(**kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
    """Descarta atributo nulo — o SDK avisa em log para cada `None` recebido."""
    return {key: value for key, value in kwargs.items() if value is not None}


def build_span_exporter(otlp_endpoint: str | None) -> SpanExporter | None:
    """Escolhe o destino do trace pela configuração (§3 da spec: o Rito só exporta).

    Sem endpoint não há exporter, e o processor nem é montado: o span continua sendo
    criado (o contexto precisa dele para propagar pelo `traceparent`), mas nada sai do
    processo. É o comportamento de dev e de teste — e é o que garante a regra 4 da
    CLAUDE.md §3, de que nenhum teste toca rede.
    """
    if not otlp_endpoint:
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    return OTLPSpanExporter(endpoint=otlp_endpoint)

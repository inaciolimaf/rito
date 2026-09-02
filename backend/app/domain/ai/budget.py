"""Teto de gasto e cache da camada de IA (spec 090, alvo 2).

Duas peças que existem pelo mesmo motivo — IA custa dinheiro a cada chamada:

- o **orçamento** avisa em 80% e bloqueia em 100%, por escritório e por mês;
- o **cache** evita pagar duas vezes pela mesma pergunta na mesma janela.

O gasto é lido de `ai_usage` (spec 081), que já registra custo por chamada. Não há um
segundo contador para divergir do primeiro.
"""

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.invariants import not_none
from app.core.repository import BaseRepository
from app.domain.ai.models import AiBudget, AiCacheEntry, AiUsage
from app.integrations.openrouter.types import LLMResponse, Message, ToolCall, Usage

# Features em que a mesma entrada dá a mesma resposta útil — reanalisar a MESMA
# intimação é o caso real. Conversa e escrita ficam de fora: repetir a pergunta ali
# costuma significar "quero outra resposta".
CACHEABLE_FEATURES: frozenset[str] = frozenset({"publication_summary"})
CACHE_TTL = timedelta(hours=6)

# Quantas vezes a média diária histórica de uma feature precisa ser superada para virar
# alerta. Três é folgado de propósito: gasto de IA oscila com o movimento do escritório, e
# um alerta que dispara toda segunda-feira deixa de ser lido.
ANOMALY_FACTOR = 3
ANOMALY_WINDOW_DAYS = 30


class BudgetExceededError(Exception):
    """Gasto do mês estourou o teto do escritório (alvo 2) → 409 com o número."""

    def __init__(self, spent: Decimal, limit: Decimal) -> None:
        super().__init__(f"Orçamento de IA excedido: US$ {spent} de US$ {limit}.")
        self.spent = spent
        self.limit = limit


@dataclass(frozen=True)
class SpendingAnomaly:
    """Uma feature gastando hoje muito acima do que costuma gastar."""

    feature_key: str
    today_usd: Decimal
    daily_average_usd: Decimal

    @property
    def factor(self) -> float:
        return float(round(self.today_usd / self.daily_average_usd, 1))


@dataclass(frozen=True)
class BudgetStatus:
    limit_usd: Decimal | None
    spent_usd: Decimal
    alert_pct: int
    is_blocking: bool

    @property
    def used_pct(self) -> float | None:
        if self.limit_usd is None or self.limit_usd == 0:
            return None
        return float(round(self.spent_usd / self.limit_usd * 100, 1))

    @property
    def should_alert(self) -> bool:
        pct = self.used_pct
        return pct is not None and pct >= self.alert_pct

    @property
    def exceeded(self) -> bool:
        return self.limit_usd is not None and self.spent_usd >= self.limit_usd


def cache_key(feature_key: str, model: str, messages: Sequence[Message]) -> str:
    """Hash de (feature, modelo, mensagens). O conteúdo não é guardado — só a impressão
    digital, porque persistir prompt exige opt-in (regra 13 da 081)."""
    payload = json.dumps(
        {
            "feature": feature_key,
            "model": model,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AiBudgetRepository(BaseRepository[AiBudget]):
    model = AiBudget

    async def get_current(self) -> AiBudget | None:
        return (await self.session.scalars(select(AiBudget))).first()


class AiCacheRepository(BaseRepository[AiCacheEntry]):
    model = AiCacheEntry

    async def get_valid(self, key: str, *, now: datetime) -> AiCacheEntry | None:
        stmt = select(AiCacheEntry).where(
            AiCacheEntry.cache_key == key, AiCacheEntry.expires_at > now
        )
        return (await self.session.scalars(stmt)).first()


class AiBudgetService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.budgets = AiBudgetRepository(session)
        self.cache = AiCacheRepository(session)

    async def status(self, *, now: datetime | None = None) -> BudgetStatus:
        agora = now or datetime.now(UTC)
        inicio = agora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        gasto = await self.session.scalar(
            select(func.coalesce(func.sum(AiUsage.cost_usd), 0)).where(AiUsage.created_at >= inicio)
        )
        budget = await self.budgets.get_current()
        return BudgetStatus(
            limit_usd=budget.monthly_limit_usd if budget else None,
            spent_usd=Decimal(str(gasto or 0)),
            alert_pct=budget.alert_pct if budget else 80,
            is_blocking=budget.is_blocking if budget else True,
        )

    async def ensure_within_budget(self, *, now: datetime | None = None) -> BudgetStatus:
        """Chamado antes de cada ida ao modelo. Bloqueia só se o escritório pediu para
        bloquear — há quem prefira estourar a parar no meio de um prazo."""
        situacao = await self.status(now=now)
        if situacao.exceeded and situacao.is_blocking:
            raise BudgetExceededError(
                situacao.spent_usd,
                not_none(situacao.limit_usd, "só há excesso quando existe teto"),
            )
        return situacao

    async def _por_feature(self, *, desde: datetime, ate: datetime | None) -> dict[str, Decimal]:
        stmt = (
            select(AiUsage.feature_key, func.coalesce(func.sum(AiUsage.cost_usd), 0))
            .where(AiUsage.created_at >= desde)
            .group_by(AiUsage.feature_key)
        )
        if ate is not None:
            stmt = stmt.where(AiUsage.created_at < ate)
        linhas = (await self.session.execute(stmt)).all()
        return {feature_key: Decimal(str(total)) for feature_key, total in linhas}

    async def anomalies(self, *, now: datetime | None = None) -> list[SpendingAnomaly]:
        """Feature gastando hoje ≥3× a média diária dos 30 dias anteriores.

        Compara com a média DELA, não com as outras: o copiloto custa naturalmente mais
        que uma classificação, e comparar features entre si só produziria ruído. A janela
        exclui hoje — incluir o dia que está sendo julgado puxaria a média para cima e
        abafaria justamente o pico que interessa.
        """
        agora = now or datetime.now(UTC)
        inicio_hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
        inicio_janela = inicio_hoje - timedelta(days=ANOMALY_WINDOW_DAYS)

        hoje = await self._por_feature(desde=inicio_hoje, ate=None)
        historico = await self._por_feature(desde=inicio_janela, ate=inicio_hoje)

        encontrados: list[SpendingAnomaly] = []
        for feature_key, gasto_hoje in hoje.items():
            media = historico.get(feature_key, Decimal(0)) / ANOMALY_WINDOW_DAYS
            # Sem histórico não há do que se desviar: o primeiro dia de uso de uma
            # feature nova não é anomalia, é estreia.
            if media <= 0:
                continue
            if gasto_hoje >= media * ANOMALY_FACTOR:
                encontrados.append(
                    SpendingAnomaly(
                        feature_key=feature_key,
                        today_usd=gasto_hoje,
                        daily_average_usd=media,
                    )
                )
        return sorted(encontrados, key=lambda item: item.feature_key)

    async def save(
        self,
        *,
        limit_usd: Decimal | None,
        alert_pct: int,
        is_blocking: bool,
        actor_id: uuid.UUID,
    ) -> AiBudget:
        budget = await self.budgets.get_current()
        if budget is None:
            budget = AiBudget(tenant_id=self.tenant_id)
            self.session.add(budget)
        budget.monthly_limit_usd = limit_usd
        budget.alert_pct = alert_pct
        budget.is_blocking = is_blocking
        budget.updated_by = actor_id
        await self.session.flush()
        return budget

    # ------------------------------------------------------------------ cache

    async def cached(
        self, *, feature_key: str, model: str, messages: Sequence[Message]
    ) -> LLMResponse | None:
        if feature_key not in CACHEABLE_FEATURES:
            return None
        entrada = await self.cache.get_valid(
            cache_key(feature_key, model, messages), now=datetime.now(UTC)
        )
        if entrada is None:
            return None
        dados = entrada.response
        return LLMResponse(
            content=dados.get("content"),
            tool_calls=[ToolCall(**call) for call in dados.get("tool_calls", [])],
            usage=Usage(**dados.get("usage", {})),
            model=entrada.model,
            finish_reason=str(dados.get("finish_reason") or "cached"),
        )

    async def store(
        self,
        *,
        feature_key: str,
        model: str,
        messages: Sequence[Message],
        response: LLMResponse,
    ) -> None:
        if feature_key not in CACHEABLE_FEATURES or response.content is None:
            return
        chave = cache_key(feature_key, model, messages)
        existente = await self.cache.get_valid(chave, now=datetime.now(UTC))
        if existente is not None:
            return
        self.session.add(
            AiCacheEntry(
                tenant_id=self.tenant_id,
                feature_key=feature_key,
                cache_key=chave,
                model=model,
                response={
                    "content": response.content,
                    "tool_calls": [
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in response.tool_calls
                    ],
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "cost_usd": response.usage.cost_usd,
                    },
                    "finish_reason": response.finish_reason,
                },
                expires_at=datetime.now(UTC) + CACHE_TTL,
            )
        )
        await self.session.flush()

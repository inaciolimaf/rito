"""IA analítica (spec 089): perguntar métrica, saber o que fazer, ser avisado antes.

Três capacidades com uma disciplina em comum — **o modelo não decide nada sozinho**:

- no text-to-SQL, ele escreve a consulta e o guardrail decide se ela roda;
- no next-best-action, o CÓDIGO lê os sinais do processo e decide a recomendação;
- nos insights, o job é determinístico e o modelo não entra.

Onde o modelo entra, ele redige. Onde a decisão importa, a decisão é do código.
"""

import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import load_prompt
from app.core.repository import BaseRepository
from app.domain.ai.models import AiInsight, AiSqlQuery
from app.domain.ai.service import AiRunner
from app.domain.ai.sql_guard import (
    ALLOWED_RELATIONS,
    STATEMENT_TIMEOUT_MS,
    CheckedSql,
    SqlRejected,
    check_sql,
)
from app.domain.users.models import FinancialAccess, User
from app.integrations.openrouter.types import Message

logger = logging.getLogger("rito.ai.analytics")

FEATURE_KEY = "analytics"

# Regra 10: dispensar um insight silencia aquele assunto por 30 dias.
DISMISS_COOLDOWN_DAYS = 30
# Regra 9 (limiares dos insights) — os mesmos números que o produto já usa em outras
# telas: 120 dias de estagnação (spec 074) e prazo em risco nos próximos 3 dias.
STAGNATION_DAYS = 120
DEADLINE_RISK_DAYS = 3
PORTFOLIO_CONCENTRATION_PCT = 40

_SQL_SYSTEM = load_prompt("analytics_sql")

CLARIFICATION_PREFIX = "PRECISO_DE_ESCLARECIMENTO:"


class ClarificationNeeded(Exception):
    """Regra 1: pergunta ambígua devolve dúvida, não SQL chutado."""

    def __init__(self, question: str) -> None:
        super().__init__(question)
        self.question = question


@dataclass
class AskResult:
    query: AiSqlQuery
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    summary: str


@dataclass(frozen=True)
class NextAction:
    """Recomendação para um processo (regra 6). `signals` é o porquê, em dados."""

    action: str
    reason: str
    signals: dict[str, Any] = field(default_factory=dict)
    suggested_tool: str | None = None
    suggested_arguments: dict[str, Any] = field(default_factory=dict)


class AiSqlQueryRepository(BaseRepository[AiSqlQuery]):
    model = AiSqlQuery


class AiInsightRepository(BaseRepository[AiInsight]):
    model = AiInsight

    async def list_open(
        self, *, kind: str | None, severity: str | None, dismissed: bool
    ) -> Sequence[AiInsight]:
        stmt = select(AiInsight).order_by(AiInsight.created_at.desc())
        stmt = (
            stmt.where(AiInsight.dismissed_at.is_not(None))
            if dismissed
            else stmt.where(AiInsight.dismissed_at.is_(None))
        )
        if kind:
            stmt = stmt.where(AiInsight.kind == kind)
        if severity:
            stmt = stmt.where(AiInsight.severity == severity)
        return (await self.session.scalars(stmt)).all()

    async def recently_dismissed(
        self, *, kind: str, subject_id: uuid.UUID | None, now: datetime
    ) -> bool:
        """Regra 10: quem dispensou não quer ver de novo amanhã."""
        cutoff = now - timedelta(days=DISMISS_COOLDOWN_DAYS)
        stmt = select(AiInsight.id).where(
            AiInsight.kind == kind,
            AiInsight.subject_id == subject_id,
            AiInsight.dismissed_at.is_not(None),
            AiInsight.dismissed_at > cutoff,
        )
        return (await self.session.scalars(stmt)).first() is not None

    async def open_for(self, *, kind: str, subject_id: uuid.UUID | None) -> AiInsight | None:
        stmt = select(AiInsight).where(
            AiInsight.kind == kind,
            AiInsight.subject_id == subject_id,
            AiInsight.dismissed_at.is_(None),
        )
        return (await self.session.scalars(stmt)).first()


class AnalyticsService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, runner: AiRunner) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.runner = runner
        self.queries = AiSqlQueryRepository(session)
        self.insights = AiInsightRepository(session)

    # ------------------------------------------------------------- text-to-SQL

    async def generate_sql(self, question: str, *, user: User) -> CheckedSql:
        """Gera e VALIDA — sem executar (regra 3: o usuário vê o SQL antes)."""
        response = await self.runner.run(
            feature_key=FEATURE_KEY,
            messages=[
                Message(
                    role="system",
                    content=_SQL_SYSTEM.format(relations="\n".join(sorted(ALLOWED_RELATIONS))),
                ),
                Message(role="user", content=question),
            ],
            user_id=user.id,
        )
        bruto = (response.content or "").strip()
        if bruto.startswith(CLARIFICATION_PREFIX):
            duvida = bruto[len(CLARIFICATION_PREFIX) :].strip()
            await self._log(
                user=user,
                question=question,
                sql=bruto,
                allowed=False,
                reason=f"ambiguidade: {duvida}",
            )
            await self._commit_log()
            raise ClarificationNeeded(duvida)
        if bruto.startswith("```"):
            bruto = bruto.strip("`").removeprefix("sql").strip()
        try:
            checado = check_sql(
                bruto, has_financial_access=user.financial_access != FinancialAccess.NONE
            )
        except SqlRejected as exc:
            # Regra 8 do §5: a tentativa rejeitada é registrada com o motivo.
            await self._log(
                user=user, question=question, sql=bruto, allowed=False, reason=exc.reason
            )
            await self._commit_log()
            raise
        return checado

    async def run_sql(self, *, user: User, question: str, checked: CheckedSql) -> AskResult:
        """Executa numa transação **somente leitura**, com timeout e o tenant setado.

        Esta é a quarta camada de guardrail (§5, item 4): mesmo que as três anteriores
        falhassem, a conexão não consegue escrever. É a única que não depende de análise
        de texto nenhuma.
        """
        started = time.monotonic()
        # O SAVEPOINT é o que torna o modo somente-leitura reversível: o Postgres NÃO
        # deixa voltar para read-write dentro da mesma transação, mas desfaz o `SET
        # LOCAL` ao abortar a subtransação. Então a consulta roda dentro do savepoint e
        # o `ROLLBACK TO` devolve a sessão ao estado de antes — sem perder nada, porque
        # o que rodou ali foi um SELECT e as linhas já estão em memória.
        await self.session.execute(text("SAVEPOINT ai_readonly"))
        try:
            await self.session.execute(
                text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            )
            await self.session.execute(text("SET LOCAL transaction_read_only = on"))
            resultado = await self.session.execute(text(checked.sql))
            colunas = list(resultado.keys())
            linhas = [dict(zip(colunas, row, strict=True)) for row in resultado.fetchall()]
        except Exception as exc:
            await self.session.execute(text("ROLLBACK TO SAVEPOINT ai_readonly"))
            await self._log(
                user=user,
                question=question,
                sql=checked.sql,
                allowed=False,
                reason=f"falha na execução: {type(exc).__name__}",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            await self._commit_log()
            raise
        await self.session.execute(text("ROLLBACK TO SAVEPOINT ai_readonly"))

        duracao = int((time.monotonic() - started) * 1000)
        registro = await self._log(
            user=user,
            question=question,
            sql=checked.sql,
            allowed=True,
            reason=None,
            rows=len(linhas),
            duration_ms=duracao,
        )
        return AskResult(
            query=registro,
            sql=checked.sql,
            columns=colunas,
            rows=[_jsonable(linha) for linha in linhas],
            summary=_summarize(question, colunas, linhas),
        )

    async def _commit_log(self) -> None:
        """A tentativa RECUSADA precisa sobreviver à exceção que sobe — a sessão por
        request faz rollback, e justamente o registro que interessa auditar sumiria.
        Mesmo idioma da 081 (`AiRunner._commit_usage`), pelo mesmo motivo."""
        await self.session.commit()

    async def _log(
        self,
        *,
        user: User,
        question: str,
        sql: str,
        allowed: bool,
        reason: str | None,
        rows: int | None = None,
        duration_ms: int | None = None,
    ) -> AiSqlQuery:
        registro = AiSqlQuery(
            tenant_id=self.tenant_id,
            user_id=user.id,
            question=question,
            generated_sql=sql,
            was_allowed=allowed,
            rejection_reason=reason,
            row_count=rows,
            duration_ms=duration_ms,
        )
        self.session.add(registro)
        await self.session.flush()
        return registro

    # -------------------------------------------------------- next-best-action

    async def next_best_action(self, lawsuit_id: uuid.UUID, *, today: date) -> NextAction:
        """Regra 6: cinco sinais, uma recomendação — decidida por regra, não por modelo.

        A ordem das checagens é a ordem da urgência real do escritório: prazo primeiro,
        porque prazo perdido não se recupera; dinheiro por último, porque cobrança
        espera um dia.
        """
        hoje = today
        sinais = await self._signals(lawsuit_id, hoje)

        if sinais["overdue_tasks"]:
            return NextAction(
                action="Concluir as tarefas em atraso",
                reason=(f"{sinais['overdue_tasks']} tarefa(s) com prazo vencido neste processo."),
                signals=sinais,
            )
        if (
            sinais["deadline_in_days"] is not None
            and sinais["deadline_in_days"] <= DEADLINE_RISK_DAYS
        ):
            return NextAction(
                action="Cumprir o prazo mais próximo",
                reason=f"Há prazo vencendo em {sinais['deadline_in_days']} dia(s).",
                signals=sinais,
            )
        if (
            sinais["days_without_movement"] is not None
            and sinais["days_without_movement"] >= STAGNATION_DAYS
        ):
            return NextAction(
                action="Movimentar o processo",
                reason=(
                    f"Sem movimentação há {sinais['days_without_movement']} dias, "
                    f"parado na etapa {sinais['stage']}."
                ),
                signals=sinais,
                suggested_tool="create_task",
                suggested_arguments={"lawsuit_id": str(lawsuit_id)},
            )
        if not sinais["open_tasks"]:
            return NextAction(
                action="Definir a próxima tarefa",
                reason=(
                    f"O processo está na etapa {sinais['stage']} e não tem nenhuma tarefa "
                    "em aberto — ninguém está com ele."
                ),
                signals=sinais,
                suggested_tool="create_task",
                suggested_arguments={"lawsuit_id": str(lawsuit_id)},
            )
        if sinais["overdue_amount"]:
            return NextAction(
                action="Cobrar o valor em atraso",
                reason=f"Há R$ {sinais['overdue_amount']:.2f} vencidos neste processo.",
                signals=sinais,
            )
        return NextAction(
            action="Seguir o plano atual",
            reason="Sem prazo próximo, sem atraso e com tarefa em andamento.",
            signals=sinais,
        )

    async def _signals(self, lawsuit_id: uuid.UUID, hoje: date) -> dict[str, Any]:
        row = (
            await self.session.execute(
                text("""
                    SELECT s.name AS stage,
                           l.last_movement_at,
                           l.is_stagnant,
                           (SELECT count(*) FROM posts p
                             JOIN post_users pu ON pu.post_id = p.id
                            WHERE p.lawsuit_id = l.id AND pu.completed_at IS NULL) AS open_tasks,
                           (SELECT count(*) FROM posts p
                             JOIN post_users pu ON pu.post_id = p.id
                            WHERE p.lawsuit_id = l.id AND pu.completed_at IS NULL
                              AND p.deadline_date < :hoje) AS overdue_tasks,
                           (SELECT min(p.deadline_date) FROM posts p
                             JOIN post_users pu ON pu.post_id = p.id
                            WHERE p.lawsuit_id = l.id AND pu.completed_at IS NULL
                              AND p.deadline_date >= :hoje) AS next_deadline,
                           (SELECT coalesce(sum(t.amount), 0) FROM transactions t
                            WHERE t.lawsuit_id = l.id AND t.kind = 'RECEITA'
                              AND t.payment_date IS NULL AND t.due_date < :hoje
                              AND NOT t.is_internal) AS overdue_amount
                    FROM lawsuits l
                    JOIN stages s ON s.id = l.stage_id
                    WHERE l.id = :lawsuit_id
                    """),
                {"lawsuit_id": lawsuit_id, "hoje": hoje},
            )
        ).first()
        if row is None:
            raise LookupError("Processo não encontrado neste escritório.")
        sem_movimento = (hoje - row.last_movement_at.date()).days if row.last_movement_at else None
        return {
            "stage": row.stage,
            "days_without_movement": sem_movimento,
            "is_stagnant": bool(row.is_stagnant),
            "open_tasks": int(row.open_tasks),
            "overdue_tasks": int(row.overdue_tasks),
            "deadline_in_days": (row.next_deadline - hoje).days if row.next_deadline else None,
            "overdue_amount": float(row.overdue_amount or 0),
        }

    # -------------------------------------------------------------- insights

    async def refresh_insights(self, *, today: date) -> int:
        """Job dos insights (regras 8, 9 e 12): determinístico, sem modelo nenhum.

        Insight é aviso sobre dado — se dependesse de LLM, custaria token por dia e
        variaria de texto sem que nada tivesse mudado no escritório.
        """
        hoje = today
        agora = datetime.now(UTC)
        criados = 0
        for kind, linhas in (
            ("deadline_risk", await self._deadline_rows(hoje)),
            ("stagnation", await self._stagnation_rows(hoje)),
            ("overdue", await self._overdue_rows(hoje)),
            ("portfolio", await self._portfolio_rows()),
        ):
            for dados in linhas:
                subject_id = dados.get("subject_id")
                if await self.insights.recently_dismissed(
                    kind=kind, subject_id=subject_id, now=agora
                ):
                    continue
                if await self.insights.open_for(kind=kind, subject_id=subject_id) is not None:
                    continue
                self.session.add(
                    AiInsight(
                        tenant_id=self.tenant_id,
                        kind=kind,
                        severity=dados["severity"],
                        subject_type=dados.get("subject_type"),
                        subject_id=subject_id,
                        title=dados["title"],
                        body=dados["body"],
                        suggested_action=dados.get("suggested_action"),
                    )
                )
                criados += 1
        await self.session.flush()
        return criados

    async def dismiss(self, insight: AiInsight, *, user: User) -> AiInsight:
        insight.dismissed_by = user.id
        insight.dismissed_at = datetime.now(UTC)
        await self.session.flush()
        return insight

    async def _deadline_rows(self, hoje: date) -> list[dict[str, Any]]:
        rows = (
            await self.session.execute(
                text("""
                    SELECT p.lawsuit_id, min(p.deadline_date) AS prazo, count(*) AS tarefas
                    FROM posts p JOIN post_users pu ON pu.post_id = p.id
                    WHERE pu.completed_at IS NULL AND p.deadline_date IS NOT NULL
                      AND p.deadline_date BETWEEN :hoje AND :limite
                    GROUP BY p.lawsuit_id
                    """),
                {"hoje": hoje, "limite": hoje + timedelta(days=DEADLINE_RISK_DAYS)},
            )
        ).all()
        return [
            {
                "severity": "critical",
                "subject_type": "lawsuit",
                "subject_id": row.lawsuit_id,
                "title": "Prazo vencendo",
                "body": (
                    f"{row.tarefas} tarefa(s) com prazo em {row.prazo.isoformat()} neste processo."
                ),
                "suggested_action": {"kind": "open_lawsuit", "lawsuit_id": str(row.lawsuit_id)},
            }
            for row in rows
        ]

    async def _stagnation_rows(self, hoje: date) -> list[dict[str, Any]]:
        rows = (
            await self.session.execute(
                text("""
                    SELECT l.id, s.name AS stage, l.last_movement_at
                    FROM lawsuits l JOIN stages s ON s.id = l.stage_id
                    WHERE NOT l.is_archived
                      AND (l.last_movement_at IS NULL OR l.last_movement_at < :cutoff)
                      AND l.created_at < :cutoff
                    LIMIT 50
                    """),
                {"cutoff": hoje - timedelta(days=STAGNATION_DAYS)},
            )
        ).all()
        return [
            {
                "severity": "warning",
                "subject_type": "lawsuit",
                "subject_id": row.id,
                "title": "Processo parado",
                "body": (
                    f"Sem movimentação há mais de {STAGNATION_DAYS} dias, na etapa {row.stage}."
                ),
                "suggested_action": {"kind": "create_task", "lawsuit_id": str(row.id)},
            }
            for row in rows
        ]

    async def _overdue_rows(self, hoje: date) -> list[dict[str, Any]]:
        rows = (
            await self.session.execute(
                text("""
                    SELECT t.customer_id, sum(t.amount) AS total, count(*) AS lancamentos
                    FROM transactions t
                    WHERE t.kind = 'RECEITA' AND t.payment_date IS NULL
                      AND t.due_date < :hoje AND NOT t.is_internal
                      AND t.customer_id IS NOT NULL
                    GROUP BY t.customer_id
                    HAVING sum(t.amount) > 0
                    LIMIT 50
                    """),
                {"hoje": hoje},
            )
        ).all()
        return [
            {
                "severity": "warning",
                "subject_type": "customer",
                "subject_id": row.customer_id,
                "title": "Inadimplência relevante",
                "body": (
                    f"R$ {float(row.total):.2f} em {row.lancamentos} lançamento(s) "
                    "vencidos deste cliente."
                ),
                "suggested_action": {"kind": "open_customer", "customer_id": str(row.customer_id)},
            }
            for row in rows
        ]

    async def _portfolio_rows(self) -> list[dict[str, Any]]:
        rows = (await self.session.execute(text("""
                    SELECT ag.id, ag.name,
                           count(*) AS processos,
                           round(100.0 * count(*) / NULLIF(sum(count(*)) OVER (), 0), 1) AS pct
                    FROM lawsuits l
                    JOIN lawsuit_types lt ON lt.id = l.lawsuit_type_id
                    JOIN action_groups ag ON ag.id = lt.action_group_id
                    WHERE NOT l.is_archived
                    GROUP BY ag.id, ag.name
                    """))).all()
        return [
            {
                "severity": "info",
                "subject_type": "action_group",
                "subject_id": row.id,
                "title": "Carteira concentrada",
                "body": (
                    f"{row.pct}% dos processos ativos estão em {row.name} — concentração "
                    "acima de {limite}%.".format(limite=PORTFOLIO_CONCENTRATION_PCT)
                ),
                "suggested_action": None,
            }
            for row in rows
            if row.pct is not None and float(row.pct) >= PORTFOLIO_CONCENTRATION_PCT
        ]


def _jsonable(row: dict[str, Any]) -> dict[str, Any]:
    convertido: dict[str, Any] = {}
    for chave, valor in row.items():
        if isinstance(valor, uuid.UUID | date | datetime):
            convertido[chave] = str(valor)
        elif hasattr(valor, "quantize"):  # Decimal
            convertido[chave] = float(valor)
        else:
            convertido[chave] = valor
    return convertido


def _summarize(question: str, columns: list[str], rows: Sequence[Any]) -> str:
    """Regra 4: além da tabela, uma frase — quem pergunta "quantos processos?" quer o
    número, não uma grade de uma célula."""
    if not rows:
        return "A consulta não devolveu nenhuma linha."
    if len(rows) == 1 and len(columns) == 1:
        valor = list(rows[0])[0] if not isinstance(rows[0], dict) else next(iter(rows[0].values()))
        return f"{columns[0]}: {valor}"
    return f"{len(rows)} linha(s) para: {question}"


__all__ = [
    "CLARIFICATION_PREFIX",
    "DISMISS_COOLDOWN_DAYS",
    "AiInsightRepository",
    "AiSqlQueryRepository",
    "AnalyticsService",
    "AskResult",
    "ClarificationNeeded",
    "NextAction",
    "SqlRejected",
]

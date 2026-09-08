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
from decimal import Decimal
from typing import Any, NoReturn

from sqlalchemy import Date, Numeric, cast, func, literal, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import ScalarSelect, Select

from app.ai.prompts import load_prompt
from app.core.repository import BaseRepository
from app.domain.action_groups.models import ActionGroup, LawsuitType
from app.domain.ai.models import AiInsight, AiSqlQuery
from app.domain.ai.service import AiRunner
from app.domain.ai.sql_guard import (
    ALLOWED_RELATIONS,
    STATEMENT_TIMEOUT_MS,
    CheckedSql,
    SqlRejected,
    check_sql,
)
from app.domain.financial.models import Transaction, TransactionKind
from app.domain.lawsuits.models import Lawsuit
from app.domain.posts.models import Post, PostUser
from app.domain.stages.models import Stage
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


# Uma consulta só, com subqueries correlacionadas, e não seis: o orçamento de queries do
# CLAUDE.md §11 conta statements, e o painel de sinais é lido dentro do detalhe do processo,
# que tem 5 no total. Fora do corpo do método porque uma consulta de 25 linhas dentro dele
# esconde o que o método faz — aqui ela é um dado nomeado, não lógica.
#
# Spec 127: era uma string de SQL; agora é o mesmo desenho montado pelo query builder. As
# quatro subqueries continuam CORRELACIONADAS (referenciam `Lawsuit.id` da consulta de
# fora, e o SQLAlchemy tira `lawsuits` do FROM delas sozinho) — se alguma deixasse de ser,
# o resultado mudaria de "deste processo" para "de todos", e o gate de orçamento de
# queries não pegaria isso porque o número de statements continuaria 1.


def _tarefas_abertas(*extra: Any) -> ScalarSelect[int]:
    """`count(*)` das tarefas do processo ainda não concluídas, com filtros extras."""
    return (
        select(func.count())
        .select_from(Post)
        .join(PostUser, PostUser.post_id == Post.id)
        .where(Post.lawsuit_id == Lawsuit.id, PostUser.completed_at.is_(None), *extra)
        .scalar_subquery()
    )


def _proximo_prazo(dia: Any) -> ScalarSelect[date | None]:
    """A menor data de prazo ainda por vencer entre as tarefas abertas do processo."""
    return (
        select(func.min(Post.deadline_date))
        .select_from(Post)
        .join(PostUser, PostUser.post_id == Post.id)
        .where(
            Post.lawsuit_id == Lawsuit.id,
            PostUser.completed_at.is_(None),
            Post.deadline_date >= dia,
        )
        .scalar_subquery()
    )


def _inadimplencia(dia: Any) -> ScalarSelect[Decimal]:
    """Receita vencida e não paga do processo — só a que é do cliente (regra 6)."""
    return (
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.lawsuit_id == Lawsuit.id,
            Transaction.kind == TransactionKind.RECEITA,
            Transaction.payment_date.is_(None),
            Transaction.due_date < dia,
            Transaction.is_internal.is_(False),
        )
        .scalar_subquery()
    )


def _sinais_query(lawsuit_id: uuid.UUID, hoje: date) -> Select[Any]:
    dia = literal(hoje, Date())
    return (
        select(
            Stage.name.label("stage"),
            Lawsuit.last_movement_at,
            Lawsuit.is_stagnant,
            _tarefas_abertas().label("open_tasks"),
            _tarefas_abertas(Post.deadline_date < dia).label("overdue_tasks"),
            _proximo_prazo(dia).label("next_deadline"),
            _inadimplencia(dia).label("overdue_amount"),
        )
        .select_from(Lawsuit)
        .join(Stage, Stage.id == Lawsuit.stage_id)
        .where(Lawsuit.id == lawsuit_id)
    )


def _inadimplentes_query(hoje: date) -> Select[Any]:
    """Receita vencida por CLIENTE (não por processo) — o insight é sobre a cobrança."""
    return (
        select(
            Transaction.customer_id,
            func.sum(Transaction.amount).label("total"),
            func.count().label("lancamentos"),
        )
        .where(
            Transaction.kind == TransactionKind.RECEITA,
            Transaction.payment_date.is_(None),
            Transaction.due_date < hoje,
            Transaction.is_internal.is_(False),
            Transaction.customer_id.is_not(None),
        )
        .group_by(Transaction.customer_id)
        .having(func.sum(Transaction.amount) > 0)
        .limit(50)
    )


def _carteira_query() -> Select[Any]:
    """Processos ativos por grupo de ação, com o percentual sobre o total.

    `100.0` como NUMERIC, não como inteiro: `100 * count(*) / total` seria divisão
    inteira e toda concentração abaixo de 100% viraria 0. Era o que o `100.0` da versão
    em string comprava, e é o que `cast(..., Numeric)` compra aqui.
    """
    processos = func.count()
    pct = func.round(
        cast(
            literal(Decimal("100.0"), Numeric)
            * processos
            / func.nullif(func.sum(processos).over(), 0),
            Numeric,
        ),
        1,
    )
    return (
        select(ActionGroup.id, ActionGroup.name, processos.label("processos"), pct.label("pct"))
        .select_from(Lawsuit)
        .join(LawsuitType, LawsuitType.id == Lawsuit.lawsuit_type_id)
        .join(ActionGroup, ActionGroup.id == LawsuitType.action_group_id)
        .where(Lawsuit.is_archived.is_(False))
        .group_by(ActionGroup.id, ActionGroup.name)
    )


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


def _recommendation(sinais: dict[str, Any], lawsuit_id: uuid.UUID) -> NextAction:
    """Regra 6: cinco sinais, uma recomendação — decidida por REGRA, não por modelo.

    A ORDEM é o produto: prazo primeiro, porque prazo perdido não se recupera; dinheiro por
    último, porque cobrança espera um dia. Ela está literalmente nesta linha, e trocar a
    posição de um termo do `or` muda o que o escritório vê primeiro.
    """
    return _deadline_action(sinais) or _flow_action(sinais, lawsuit_id) or _steady_action(sinais)


def _deadline_action(sinais: dict[str, Any]) -> NextAction | None:
    """Os dois sinais de prazo, que vêm antes de tudo (regra 6)."""
    if sinais["overdue_tasks"]:
        return NextAction(
            action="Concluir as tarefas em atraso",
            reason=(f"{sinais['overdue_tasks']} tarefa(s) com prazo vencido neste processo."),
            signals=sinais,
        )
    if sinais["deadline_in_days"] is not None and sinais["deadline_in_days"] <= DEADLINE_RISK_DAYS:
        return NextAction(
            action="Cumprir o prazo mais próximo",
            reason=f"Há prazo vencendo em {sinais['deadline_in_days']} dia(s).",
            signals=sinais,
        )
    return None


def _task_action(
    action: str, reason: str, sinais: dict[str, Any], lawsuit_id: uuid.UUID
) -> NextAction:
    """Sugestão que se resolve criando tarefa — as duas do fluxo têm a mesma ferramenta.

    A ferramenta e os argumentos são idênticos porque a ação também é: alguém do escritório
    precisa pegar o processo. O que muda é só o motivo mostrado ao usuário.
    """
    return NextAction(
        action=action,
        reason=reason,
        signals=sinais,
        suggested_tool="create_task",
        suggested_arguments={"lawsuit_id": str(lawsuit_id)},
    )


def _flow_action(sinais: dict[str, Any], lawsuit_id: uuid.UUID) -> NextAction | None:
    """Andamento e cobrança: o processo parado, o processo sem dono, e o valor vencido.

    Os dois primeiros sugerem `create_task` porque a ação é sempre a mesma — alguém precisa
    pegar o processo. O terceiro não sugere ferramenta: cobrar é decisão do escritório, e a
    IA não abre cobrança sozinha.
    """
    if (
        sinais["days_without_movement"] is not None
        and sinais["days_without_movement"] >= STAGNATION_DAYS
    ):
        return _task_action(
            "Movimentar o processo",
            f"Sem movimentação há {sinais['days_without_movement']} dias, "
            f"parado na etapa {sinais['stage']}.",
            sinais,
            lawsuit_id,
        )
    if not sinais["open_tasks"]:
        return _task_action(
            "Definir a próxima tarefa",
            f"O processo está na etapa {sinais['stage']} e não tem nenhuma tarefa "
            "em aberto — ninguém está com ele.",
            sinais,
            lawsuit_id,
        )
    if sinais["overdue_amount"]:
        return NextAction(
            action="Cobrar o valor em atraso",
            reason=f"Há R$ {sinais['overdue_amount']:.2f} vencidos neste processo.",
            signals=sinais,
        )
    return None


def _steady_action(sinais: dict[str, Any]) -> NextAction:
    """Nenhum sinal disparou. Recomendar «siga» é uma recomendação — devolver nada não é."""
    return NextAction(
        action="Seguir o plano atual",
        reason="Sem prazo próximo, sem atraso e com tarefa em andamento.",
        signals=sinais,
    )


class AnalyticsService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, runner: AiRunner) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.runner = runner
        self.queries = AiSqlQueryRepository(session)
        self.insights = AiInsightRepository(session)

    # ------------------------------------------------------------- text-to-SQL

    async def _raise_clarification(self, bruto: str, *, user: User, question: str) -> NoReturn:
        """A pergunta ambígua vira `ClarificationNeeded`, registrada como tentativa negada.

        Ambiguidade é resposta legítima do modelo, não erro — mas entra no log pelo mesmo
        motivo que o SQL rejeitado (regra 8 do §5): quem audita precisa ver o que foi
        perguntado e por que nada rodou.
        """
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
            await self._raise_clarification(bruto, user=user, question=question)
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

    async def _run_readonly(self, sql: str) -> tuple[list[str], list[dict[str, Any]]]:
        """A consulta dentro do savepoint somente-leitura, com timeout.

        Os únicos `text()` que a spec 127 deixou no domínio estão aqui, e por dois motivos
        que não têm conserto: `SET LOCAL` e `SAVEPOINT`/`ROLLBACK TO` são comandos de
        SESSÃO, que o query builder não monta porque não são consultas; e `sql` é a
        consulta que o MODELO escreveu — é o produto desta feature, e passar por um
        builder mudaria o que o usuário vê no preview e o que o guardrail acabou de
        aprovar. A defesa dela não é a montagem, é o `check_sql` + a transação
        somente-leitura (§5).

        `SET LOCAL` vale até o fim da subtransação, e é isso que torna o modo reversível:
        o Postgres NÃO deixa voltar de read-only para read-write dentro da mesma
        transação, mas desfaz o `SET LOCAL` ao abortar o savepoint.
        """
        await self.session.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
        await self.session.execute(text("SET LOCAL transaction_read_only = on"))
        resultado = await self.session.execute(text(sql))
        colunas = list(resultado.keys())
        return colunas, [dict(zip(colunas, row, strict=True)) for row in resultado.fetchall()]

    async def _log_failed_run(
        self,
        exc: Exception,
        *,
        user: User,
        question: str,
        checked: CheckedSql,
        started: float,
    ) -> None:
        """Desfaz o savepoint e registra a tentativa que falhou (regra 8 do §5).

        O `ROLLBACK TO` vem ANTES do log: a sessão está abortada enquanto o savepoint não
        volta, e um `INSERT` de auditoria numa transação abortada falharia — trocando o erro
        real do usuário por um erro do próprio código de auditoria.
        """
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

    async def run_sql(self, *, user: User, question: str, checked: CheckedSql) -> AskResult:
        """Executa numa transação **somente leitura**, com timeout e o tenant setado.

        Esta é a quarta camada de guardrail (§5, item 4): mesmo que as três anteriores
        falhassem, a conexão não consegue escrever. É a única que não depende de análise
        de texto nenhuma.

        O SAVEPOINT é o que torna o modo reversível — o porquê está em `_run_readonly`. O
        `ROLLBACK TO` no fim não perde nada: o que rodou ali foi um SELECT, e as linhas já
        estão em memória quando ele acontece.
        """
        started = time.monotonic()
        await self.session.execute(text("SAVEPOINT ai_readonly"))
        try:
            colunas, linhas = await self._run_readonly(checked.sql)
        except Exception as exc:
            await self._log_failed_run(
                exc, user=user, question=question, checked=checked, started=started
            )
            raise
        await self.session.execute(text("ROLLBACK TO SAVEPOINT ai_readonly"))

        registro = await self._log(
            user=user,
            question=question,
            sql=checked.sql,
            allowed=True,
            reason=None,
            rows=len(linhas),
            duration_ms=int((time.monotonic() - started) * 1000),
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
        sinais = await self._signals(lawsuit_id, today)
        return _recommendation(sinais, lawsuit_id)

    async def _signals(self, lawsuit_id: uuid.UUID, hoje: date) -> dict[str, Any]:
        row = (await self.session.execute(_sinais_query(lawsuit_id, hoje))).first()
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

    async def _add_insights(
        self, kind: str, linhas: Sequence[dict[str, Any]], agora: datetime
    ) -> int:
        """Cria os insights de um tipo, pulando os que o escritório já viu.

        Duas razões para pular, e as duas importam (regra 9): o insight foi dispensado há
        pouco — reabri-lo todo dia transforma aviso em ruído —, ou já existe um aberto para
        o mesmo assunto, e dois avisos idênticos na tela é pior que um.
        """
        criados = 0
        for dados in linhas:
            subject_id = dados.get("subject_id")
            if await self.insights.recently_dismissed(kind=kind, subject_id=subject_id, now=agora):
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
        return criados

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
            criados += await self._add_insights(kind, linhas, agora)
        await self.session.flush()
        return criados

    async def dismiss(self, insight: AiInsight, *, user: User) -> AiInsight:
        insight.dismissed_by = user.id
        insight.dismissed_at = datetime.now(UTC)
        await self.session.flush()
        return insight

    async def _deadline_rows(self, hoje: date) -> list[dict[str, Any]]:
        consulta = (
            select(
                Post.lawsuit_id,
                func.min(Post.deadline_date).label("prazo"),
                func.count().label("tarefas"),
            )
            .select_from(Post)
            .join(PostUser, PostUser.post_id == Post.id)
            .where(
                PostUser.completed_at.is_(None),
                Post.deadline_date.is_not(None),
                Post.deadline_date.between(hoje, hoje + timedelta(days=DEADLINE_RISK_DAYS)),
            )
            .group_by(Post.lawsuit_id)
        )
        rows = (await self.session.execute(consulta)).all()
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
        # `literal(..., Date())` e não o `date` cru: sem o tipo, o parâmetro chega ao
        # asyncpg sem nada que diga o que ele é, e a comparação com uma coluna
        # `timestamptz` fica dependendo de inferência. Com o tipo, é o Postgres que
        # promove a data — exatamente o que a versão em string fazia.
        cutoff = literal(hoje - timedelta(days=STAGNATION_DAYS), Date())
        consulta = (
            select(Lawsuit.id, Stage.name.label("stage"), Lawsuit.last_movement_at)
            .select_from(Lawsuit)
            .join(Stage, Stage.id == Lawsuit.stage_id)
            .where(
                Lawsuit.is_archived.is_(False),
                or_(Lawsuit.last_movement_at.is_(None), Lawsuit.last_movement_at < cutoff),
                Lawsuit.created_at < cutoff,
            )
            .limit(50)
        )
        rows = (await self.session.execute(consulta)).all()
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
        rows = (await self.session.execute(_inadimplentes_query(hoje))).all()
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
        rows = (await self.session.execute(_carteira_query())).all()
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

"""A fronteira do text-to-SQL, no banco (spec 133 §5).

Estes testes atacam a camada 4 do §5 da spec 089 com o guardrail de texto DESLIGADO — a
`CheckedSql` é montada à mão, sem passar pelo `check_sql`. É de propósito: a spec 089
promete quatro camadas independentes, e a única forma de provar que a quarta vale sozinha
é entregar a ela um SQL que a primeira teria recusado.

O ataque é o que foi medido no HEAD antes desta spec: `set_config('app.tenant_id', <outro
escritório>, true)` dentro de uma subconsulta em `OFFSET`. O Postgres avalia esse InitPlan
ANTES de varrer a relação; as views barreira leem `current_setting('app.tenant_id')`
depois. A sessão do escritório A recebia a linha do escritório B, e o
`transaction_read_only = on` não via nada de errado — `set_config` não é escrita.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.ai.analytics import AnalyticsService
from app.domain.ai.models import AiSqlQuery
from app.domain.ai.service import AiRunner
from app.domain.ai.sql_guard import ALLOWED_RELATIONS, CheckedSql
from app.domain.users.models import FinancialAccess, User, UserRole
from tests.integration.conftest import SeededUser
from tests.integration.test_ai_copilot import ScriptedProvider
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)

# As mesmas 9 relações que a migration 133 libera para `rito_ai`. Escritas aqui à mão pelo
# mesmo motivo que o vocabulário financeiro do `test_sql_guard` é: uma lista que o teste
# derivasse da constante passaria verde no dia em que alguém apagasse uma linha das duas.
RELACOES_LIBERADAS = {
    "ai_allowed_metrics",
    "bi_pipeline_monthly_visible",
    "bi_vintage_visible",
    "bi_lawsuit_cycles_visible",
    "bi_cost_allocation_visible",
    "user_monthly_scores_visible",
    "account_daily_balances_visible",
    "agility_daily_visible",
    "timesheet_daily_visible",
}


def _checked(sql: str) -> CheckedSql:
    """Um `CheckedSql` que NÃO passou pelo guarda — o ponto do arquivo inteiro."""
    return CheckedSql(sql=sql, relations=["ai_allowed_metrics"], touches_financial=False)


def _service(session: AsyncSession, user: User) -> AnalyticsService:
    return AnalyticsService(
        session=session,
        tenant_id=user.tenant_id,
        runner=AiRunner(session, user.tenant_id, ScriptedProvider()),
    )


async def _actor(session: AsyncSession, user: SeededUser) -> User:
    await set_tenant_context(session, user.tenant_id)
    quem = await session.get(User, user.user_id)
    assert quem is not None
    return quem


@pytest.fixture
async def admin(make_user: Callable[..., Awaitable[SeededUser]]) -> SeededUser:
    return await make_user(role=UserRole.ADMINISTRADOR, financial_access=FinancialAccess.FULL)


async def test_troca_de_tenant_no_offset_morre_por_falta_de_privilegio(
    admin: SeededUser, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """O achado crítico da auditoria, com o guarda desligado.

    Antes da 133 esta consulta rodava e devolvia a linha do outro escritório. Agora ela
    morre em `permission denied for function set_config`, porque o papel corrente durante a
    consulta do modelo é `rito_ai` — que não tem `EXECUTE` nessa função. A troca não é
    detectada depois: ela não acontece.
    """
    vizinho = uuid.uuid4()
    sql = (
        "SELECT month FROM ai_allowed_metrics LIMIT 1000 OFFSET "
        f"(SELECT 0 FROM (SELECT set_config('app.tenant_id', '{vizinho}', true)) AS z)"
    )
    async with app_session_factory() as session, session.begin():
        quem = await _actor(session, admin)
        with pytest.raises(Exception, match="permission denied for function set_config"):
            await _service(session, quem).run_sql(
                user=quem, question="quantos processos?", checked=_checked(sql)
            )


async def test_a_tentativa_falha_e_a_sessao_volta_inteira(
    admin: SeededUser, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A tentativa falha E não deixa resíduo — e quem prova isso é o log da própria falha.

    Depois do erro, `run_sql` faz `ROLLBACK TO SAVEPOINT` e grava a tentativa em
    `ai_sql_queries` (regra 8 do §5). Esse `INSERT` é o teste do estado da sessão, e testa
    as duas metades de uma vez: se o papel `rito_ai` tivesse vazado do savepoint, ele
    morreria em *permission denied* (o papel não tem `INSERT` em nada); se o
    `app.tenant_id` tivesse ficado trocado, ele morreria no `WITH CHECK` da política de
    RLS. A linha existir, com o tenant certo, é a prova de que nem um nem outro sobreviveu.
    """
    vizinho = uuid.uuid4()
    sql = (
        "SELECT month FROM ai_allowed_metrics OFFSET "
        f"(SELECT 0 FROM (SELECT set_config('app.tenant_id', '{vizinho}', true)) AS z)"
    )
    async with app_session_factory() as session, session.begin():
        quem = await _actor(session, admin)
        with pytest.raises(Exception, match="permission denied"):
            await _service(session, quem).run_sql(
                user=quem, question="quantos processos?", checked=_checked(sql)
            )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, admin.tenant_id)
        registro = (await session.scalars(select(AiSqlQuery))).one()

    assert registro.was_allowed is False
    assert registro.tenant_id == admin.tenant_id
    assert registro.rejection_reason is not None


@pytest.mark.parametrize(
    ("sql", "veneno"),
    [
        (
            "SELECT month FROM ai_allowed_metrics WHERE "
            "set_config('app.tenant_id', '{t}', true) IS NOT NULL",
            "no WHERE",
        ),
        (
            "SELECT month FROM ai_allowed_metrics GROUP BY month HAVING count(*) >= "
            "length(set_config('app.tenant_id', '{t}', true))",
            "no HAVING",
        ),
        (
            "SELECT month FROM ai_allowed_metrics "
            "ORDER BY set_config('app.tenant_id', '{t}', true)",
            "no ORDER BY",
        ),
        (
            "SELECT month, (SELECT set_config('app.tenant_id', '{t}', true)) "
            "FROM ai_allowed_metrics",
            "numa subconsulta escalar",
        ),
    ],
)
async def test_nenhum_lugar_da_consulta_troca_o_tenant(
    sql: str,
    veneno: str,
    admin: SeededUser,
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`OFFSET` foi por onde alguém entrou; não é por onde a defesa termina.

    O privilégio não distingue cláusula: a função é a mesma em qualquer ponto da árvore, e
    quem a chama é o papel corrente. Os quatro casos existem porque a camada de texto os
    trata um a um e a de banco os trata de uma vez — e é essa diferença que faz as duas
    valerem a pena juntas.
    """
    alvo = sql.format(t=uuid.uuid4())
    async with app_session_factory() as session, session.begin():
        quem = await _actor(session, admin)
        with pytest.raises(Exception, match="permission denied for function set_config"):
            await _service(session, quem).run_sql(
                user=quem, question=f"tentativa {veneno}", checked=_checked(alvo)
            )


async def test_a_consulta_legitima_continua_rodando_no_papel_restrito(
    admin: SeededUser, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A defesa não pode custar a feature: o catálogo de indicadores continua legível."""
    async with app_session_factory() as session, session.begin():
        quem = await _actor(session, admin)
        resultado = await _service(session, quem).run_sql(
            user=quem,
            question="quantos processos por mês?",
            checked=_checked("SELECT month, lawsuits FROM ai_allowed_metrics LIMIT 1000"),
        )

    assert resultado.columns == ["month", "lawsuits"]


async def test_tabela_crua_nao_e_legivel_pelo_papel_da_ia(
    admin: SeededUser, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """A allowlist de relações deixa de ser só análise estática e vira privilégio.

    `customers` não está entre os `GRANT`s da migration 133. Mesmo que o parser deixasse
    passar — e ele não deixa —, o banco recusa. É a diferença entre "o guarda não conhece
    esta forma" e "esta leitura não existe para este papel".
    """
    async with app_session_factory() as session, session.begin():
        quem = await _actor(session, admin)
        with pytest.raises(Exception, match="permission denied for table customers"):
            await _service(session, quem).run_sql(
                user=quem,
                question="quem são os clientes?",
                checked=_checked("SELECT name FROM customers LIMIT 10"),
            )


async def test_o_papel_da_ia_le_exatamente_o_catalogo_da_allowlist(
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """As duas listas — a do `sql_guard` e a dos `GRANT`s — dizem a mesma coisa.

    Elas são escritas duas vezes de propósito (a migration explica por quê: `GRANT` de
    banco já migrado não muda porque uma constante do Python mudou). Este teste é o que
    torna a duplicação segura: relação nova na allowlist sem `GRANT` correspondente vira
    uma consulta que passa no guarda e morre no banco, e o contrário deixa um privilégio
    aberto que ninguém pediu.
    """
    consulta = text(
        "SELECT c.relname FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' "
        "AND has_table_privilege('rito_ai', c.oid, 'SELECT') "
        "AND c.relkind IN ('v', 'm')"
    )
    async with app_session_factory() as session, session.begin():
        concedidas: set[Any] = set((await session.scalars(consulta)).all())

    assert set(ALLOWED_RELATIONS) == RELACOES_LIBERADAS
    assert concedidas >= RELACOES_LIBERADAS, "relação do catálogo sem GRANT para rito_ai"
    assert concedidas <= RELACOES_LIBERADAS, "view liberada para rito_ai fora do catálogo"


async def _um_processo(client: AsyncClient, user: SeededUser) -> None:
    """Um processo completo do escritório — o suficiente para a view somar 1."""
    headers = _auth_header(user)
    type_id, _grupo = await _create_lawsuit_type(client, headers)
    stage_id = await _create_stage(client, headers)
    customer_id = await _create_customer(client, headers, "Cliente do isolamento")
    await _create_lawsuit(
        client,
        headers,
        user_id=str(user.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        parties=[{"customer_id": customer_id, "pole": "ATIVO", "is_client": True}],
    )


async def test_o_escritorio_a_nao_soma_o_processo_do_escritorio_b(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O teste do §4 do `CLAUDE.md`, pelo caminho da IA — e ele importa mais depois da 133.

    `ai_allowed_metrics` é `security_invoker=true`: quem isola é o RLS de `lawsuits`, e a
    migration 133 deu a `rito_ai` o `SELECT` nessa tabela. Se o papel novo tivesse nascido
    `BYPASSRLS` — ou se o `GRANT` fosse a única coisa entre ele e a tabela — este número
    viria 2. Ele vem 1.
    """
    dono = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    vizinho = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    await _um_processo(client, dono)
    await _um_processo(client, vizinho)

    async with app_session_factory() as session, session.begin():
        quem = await _actor(session, dono)
        resultado = await _service(session, quem).run_sql(
            user=quem,
            question="quantos processos o escritório tem?",
            checked=_checked("SELECT sum(lawsuits) AS total FROM ai_allowed_metrics LIMIT 1000"),
        )

    assert [linha["total"] for linha in resultado.rows] == [1]

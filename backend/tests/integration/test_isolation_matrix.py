"""Auditoria de isolamento entre tenants (spec 080, alvo 1).

A spec 079 abriu a primeira exceção legítima à regra "nenhum dado atravessa a
fronteira do tenant". Estes testes existem para que a exceção continue sendo UMA, e
conhecida: eles leem o catálogo do Postgres e comparam com a lista documentada em
`docs/SEGURANCA-RLS.md`. Política nova, tabela nova sem RLS ou exceção não documentada
quebram aqui — não num relatório, seis specs depois.
"""

import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context

SessionFactory = async_sessionmaker[AsyncSession]

APP_DIR = Path(__file__).resolve().parents[2] / "app"
SECURITY_DOC = Path(__file__).resolve().parents[3] / "docs" / "SEGURANCA-RLS.md"

_CURRENT_TENANT = "(current_setting('app.tenant_id'::text, true))::uuid"

# A política padrão que `enable_rls_statements` escreve — 52 das 56 políticas do banco.
_CANONICAL_QUAL = f"(tenant_id = {_CURRENT_TENANT})"

# As ÚNICAS exceções permitidas. Cada chave precisa aparecer em docs/SEGURANCA-RLS.md
# com a justificativa; cada uma tem um teste de comportamento neste arquivo ou em
# test_partnerships.py. Acrescentar uma linha aqui é uma decisão de segurança.
DOCUMENTED_EXCEPTIONS: dict[tuple[str, str], str] = {
    ("external_requests", "tenant_isolation"): (
        "Auditoria de chamada externa (spec 050): a linha de uma chamada de sistema "
        "(sync agendada) nasce sem tenant — `tenant_id IS NULL` é visível a todos."
    ),
    ("integration_alerts", "tenant_isolation"): (
        "Alerta global de integração (spec 049): saúde do DJEN/DataJud é do sistema, "
        "não de um escritório — `tenant_id IS NULL` é visível a todos."
    ),
    ("legal_agents", "tenant_isolation"): (
        "Spec 087: os 19 agentes de petição são catálogo GLOBAL (tenant nulo), como "
        "courts e steps; o escritório enxerga os de sistema e os seus, e só escreve "
        "nos seus (WITH CHECK sem o `IS NULL`)."
    ),
    ("partnerships", "partnerships_read"): (
        "Spec 079: a parceria pertence aos dois escritórios, então as duas pontas leem."
    ),
    ("partnerships", "partnerships_write"): (
        "Spec 079: só quem convidou escreve; aceitar/encerrar passam por função."
    ),
    ("shared_lawsuits", "shared_lawsuits_read"): (
        "Spec 079: o compartilhamento é visível ao dono e ao parceiro."
    ),
    ("shared_lawsuits", "shared_lawsuits_write"): (
        "Spec 079: só o dono cria, altera ou revoga o compartilhamento."
    ),
}


async def _scalar(session: AsyncSession, sql: str) -> object:
    return (await session.execute(text(sql))).scalar()


async def test_toda_tabela_com_tenant_id_tem_rls_ligado_e_forcado(
    app_session_factory: SessionFactory,
) -> None:
    """CLAUDE.md §4: `ENABLE` sem `FORCE` deixaria o dono da tabela ler tudo."""
    async with app_session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' "
                    "AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid "
                    "  AND a.attname = 'tenant_id' AND NOT a.attisdropped)"
                )
            )
        ).all()

    assert rows, "nenhuma tabela com tenant_id encontrada — o scanner está quebrado"
    desprotegidas = [row.relname for row in rows if not (row[1] and row[2])]
    assert desprotegidas == [], f"tabela com tenant_id sem RLS forçado: {desprotegidas}"


async def test_toda_tabela_com_rls_tem_politica(app_session_factory: SessionFactory) -> None:
    """RLS ligado sem política nenhuma esconde tudo — e o bug só aparece em produção."""
    async with app_session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity "
                    "AND NOT EXISTS (SELECT 1 FROM pg_policies p WHERE p.tablename = c.relname)"
                )
            )
        ).all()
    assert [row.relname for row in rows] == []


async def test_toda_excecao_de_politica_esta_documentada(
    app_session_factory: SessionFactory,
) -> None:
    """O coração da auditoria: qualquer política que não seja o isolamento padrão tem
    que estar na lista acima E no documento — as duas coisas, não uma."""
    async with app_session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT tablename, policyname, qual, with_check FROM pg_policies "
                    "ORDER BY tablename, policyname"
                )
            )
        ).all()

    excecoes = {
        (row.tablename, row.policyname)
        for row in rows
        if row.qual != _CANONICAL_QUAL or (row.with_check or _CANONICAL_QUAL) != _CANONICAL_QUAL
    }

    assert excecoes == set(DOCUMENTED_EXCEPTIONS), (
        "exceção de RLS não documentada (ou documentada e removida). "
        f"No banco: {sorted(excecoes)}; documentadas: {sorted(DOCUMENTED_EXCEPTIONS)}"
    )

    doc = SECURITY_DOC.read_text(encoding="utf-8")
    faltando = [
        f"{table}.{policy}"
        for table, policy in DOCUMENTED_EXCEPTIONS
        if f"`{table}`" not in doc or f"`{policy}`" not in doc
    ]
    assert faltando == [], f"exceção sem justificativa em docs/SEGURANCA-RLS.md: {faltando}"


async def test_role_da_aplicacao_nao_ignora_rls(app_session_factory: SessionFactory) -> None:
    """Se a aplicação rodasse com BYPASSRLS, toda política acima seria decoração."""
    async with app_session_factory() as session:
        row = (
            await session.execute(
                text(
                    "SELECT current_user AS role, rolbypassrls, rolsuper FROM pg_roles "
                    "WHERE rolname = current_user"
                )
            )
        ).one()

    assert row.role == "rito_app"
    assert row.rolbypassrls is False
    assert row.rolsuper is False


def test_nenhum_modulo_da_app_troca_de_role_ou_usa_conexao_de_migration() -> None:
    """`SET ROLE` ou a URL de migration em runtime desligariam o RLS por dentro.

    A exceção conhecida é o refresh de view materializada (spec 060/078), que roda no
    worker: `REFRESH MATERIALIZED VIEW CONCURRENTLY` não roda sob FORCE RLS. Ele vive
    em `app/core/materialized_view.py` e em `app/workers/`, nunca no caminho de request.
    """
    ofensores: list[str] = []
    for path in APP_DIR.rglob("*.py"):
        conteudo = path.read_text(encoding="utf-8")
        relativo = str(path.relative_to(APP_DIR.parent))
        if re.search(r"\bSET\s+ROLE\b", conteudo, re.IGNORECASE):
            ofensores.append(f"{relativo}: SET ROLE")
        if "migrations_database_url" in conteudo and not (
            relativo.startswith("app/workers/")
            or relativo in ("app/core/materialized_view.py", "app/core/config.py", "app/core/db.py")
        ):
            ofensores.append(f"{relativo}: conexão de migration fora do worker")
    assert ofensores == [], ofensores


async def test_matriz_leitura_escrita_por_tenant(
    app_session_factory: SessionFactory, tenant_probe_table: str
) -> None:
    """A matriz do alvo 1: para a mesma linha, o tenant B não lê, não atualiza, não
    apaga e não insere no lugar do tenant A. Roda sobre a tabela-sonda porque ela
    exercita a política padrão — a mesma que 52 das 56 políticas usam, gerada pela
    mesma função (`enable_rls_statements`)."""
    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_a)
        await session.execute(
            text(f"INSERT INTO {tenant_probe_table} (tenant_id, label) VALUES (:t, 'linha-a')"),
            {"t": str(tenant_a)},
        )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_b)
        assert await _scalar(session, f"SELECT count(*) FROM {tenant_probe_table}") == 0

        atualizadas = await session.execute(
            text(f"UPDATE {tenant_probe_table} SET label = 'invadida' RETURNING id")
        )
        assert atualizadas.all() == []

        apagadas = await session.execute(text(f"DELETE FROM {tenant_probe_table} RETURNING id"))
        assert apagadas.all() == []

    async with app_session_factory() as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await set_tenant_context(session, tenant_b)
                await session.execute(
                    text(
                        f"INSERT INTO {tenant_probe_table} (tenant_id, label) "
                        "VALUES (:t, 'forjada')"
                    ),
                    {"t": str(tenant_a)},
                )

    # A linha do tenant A sobreviveu intacta às quatro tentativas.
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_a)
        labels = (await session.execute(text(f"SELECT label FROM {tenant_probe_table}"))).scalars()
        assert list(labels) == ["linha-a"]

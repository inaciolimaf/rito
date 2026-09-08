"""As colunas declaradas em Python batem com as das funções do banco (spec 127).

A 127 trocou `SELECT * FROM f(:x)` por `select(func.f(x).table_valued(*colunas))`. A
diferença prática é que os nomes das colunas passaram a ser um dado do módulo Python —
`COLUNAS_SHARE_FOR`, `COLUNAS_TOKEN_LOOKUP`, `COLUNAS_ICAL_FEED` — em vez de ficarem
implícitos no `*`.

Isso é melhor de duas formas e pior de uma. Melhor porque o contrato fica visível e
porque o `mypy` passa a ver os acessos; pior porque agora existem DUAS fontes para o
mesmo fato: a migration que criou a função e a tupla que a chama. Este teste é o que
impede as duas de divergirem — mesmo idioma do
`test_cabecalho_de_cada_spec_concorda_com_o_roadmap` (spec 100) e do
`test_enum_mirror.py` (spec 124): duas fontes, uma conferida contra a outra.

Sem ele, renomear uma coluna numa função `SECURITY DEFINER` continuaria compilando, e o
erro só apareceria quando o endpoint de parceria rodasse.
"""

import uuid
from typing import Any

import pytest
from sqlalchemy import Text, func, literal, select, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.api_tokens.service import COLUNAS_TOKEN_LOOKUP
from app.domain.partnerships.sharing import (
    COLUNAS_PENDING_DEMANDS,
    COLUNAS_SHARE_FOR,
    COLUNAS_SHARED_LAWSUITS,
    COLUNAS_SHARED_PARTIES,
    COLUNAS_SHARED_TASK_TYPES,
    COLUNAS_SHARED_TASKS,
    COLUNAS_SHARED_TIMELINE,
)
from app.domain.schedule.service import COLUNAS_ICAL_FEED

# (função no banco, tupla declarada no Python que a chama)
CONTRATOS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("partner_share_for", COLUNAS_SHARE_FOR),
    ("partner_shared_lawsuits", COLUNAS_SHARED_LAWSUITS),
    ("partner_shared_parties", COLUNAS_SHARED_PARTIES),
    ("partner_shared_timeline", COLUNAS_SHARED_TIMELINE),
    ("partner_shared_tasks", COLUNAS_SHARED_TASKS),
    ("partner_shared_task_types", COLUNAS_SHARED_TASK_TYPES),
    ("partner_pending_demands", COLUNAS_PENDING_DEMANDS),
    ("api_token_lookup", COLUNAS_TOKEN_LOOKUP),
    ("lookup_ical_feed", COLUNAS_ICAL_FEED),
)

# `proargmodes` marca cada argumento: 'i' entrada, 'o' saída, 't' coluna de RETURNS TABLE.
# Quando é NULL, a função só tem argumentos de entrada — e aí não há coluna nenhuma para
# conferir, que é o caso que o teste denuncia como "função sumiu ou mudou de forma".
#
# `::text[]` no modo porque a coluna é `"char"[]`, e o asyncpg devolve `[b'i', b't']` —
# comparar `bytes` com `str` não dá erro, dá lista vazia.
_COLUNAS_DA_FUNCAO = text("""
    SELECT p.proargnames, p.proargmodes::text[] AS modos
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'public' AND p.proname = :nome
    """)


async def _colunas_no_banco(engine: AsyncEngine, nome: str) -> list[str]:
    async with engine.connect() as conn:
        linha = (await conn.execute(_COLUNAS_DA_FUNCAO, {"nome": nome})).first()
    assert linha is not None, f"função {nome}() não existe no banco"
    nomes, modos = linha.proargnames, linha.modos
    assert modos is not None, f"{nome}() não declara colunas de saída (RETURNS TABLE)"
    return [nome_col for nome_col, modo in zip(nomes, modos, strict=True) if modo == "t"]


# Argumentos que não casam com nada — o teste é sobre a chamada ser ACEITA, não sobre o
# resultado. Os tipos vão explícitos pelo motivo que a spec 127 descobriu no
# `partnership_email_has_account`: o Postgres resolve a sobrecarga pelo tipo do argumento,
# e um `varchar` onde a função pede `citext` (ou `text`) simplesmente não existe.
_SEM_TOKEN: Any = literal("sem-token", Text())
_INEXISTENTE: Any = literal(uuid.UUID(int=0), PGUUID(as_uuid=True))
_ARGUMENTOS: dict[str, tuple[Any, ...]] = {
    "partner_share_for": (_INEXISTENTE,),
    "partner_shared_lawsuits": (),
    "partner_shared_parties": (_INEXISTENTE,),
    "partner_shared_timeline": (_INEXISTENTE, 1),
    "partner_shared_tasks": (_INEXISTENTE,),
    "partner_shared_task_types": (_INEXISTENTE,),
    "partner_pending_demands": (),
    "api_token_lookup": (_SEM_TOKEN,),
    "lookup_ical_feed": (_SEM_TOKEN,),
}


@pytest.mark.parametrize(("funcao", "declaradas"), CONTRATOS, ids=[c[0] for c in CONTRATOS])
async def test_colunas_declaradas_batem_com_as_do_banco(
    admin_engine: AsyncEngine, funcao: str, declaradas: tuple[str, ...]
) -> None:
    assert list(declaradas) == await _colunas_no_banco(admin_engine, funcao), (
        f"a tupla que chama {funcao}() no Python não bate com o RETURNS TABLE da migration "
        "— uma das duas mudou sem a outra"
    )


async def test_toda_funcao_declarada_responde_de_verdade(admin_engine: AsyncEngine) -> None:
    """As de leitura por processo respondem (vazio) para um id inexistente.

    Conferir o `pg_proc` prova que os NOMES batem; isto prova que a chamada montada pelo
    builder é aceita pelo Postgres — que é onde a spec 127 errou primeiro (o
    `partnership_email_has_account` recebia `varchar` e a função é de `citext`).
    """
    async with admin_engine.connect() as conn:
        await conn.execute(select(func.set_config("app.tenant_id", str(uuid.uuid4()), True)))
        for nome, colunas in CONTRATOS:
            chamada = getattr(func, nome)(*_ARGUMENTOS[nome])
            await conn.execute(select(chamada.table_valued(*colunas)))

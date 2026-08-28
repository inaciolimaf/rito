"""Spec 098 — invariantes de performance que valem para o projeto inteiro.

São gates estruturais: não medem uma rota, medem uma propriedade que precisa continuar
verdadeira em todo código novo. Rodam em todo PR (regra 11) porque são baratos — o mais
caro deles é uma consulta ao catálogo do Postgres.
"""

import ast
import re
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

APP = Path(__file__).resolve().parents[2] / "app"

# A mesma consulta que gerou a migration 098_fk_indexes. Uma FK é considerada coberta
# quando existe índice cujas PRIMEIRAS colunas são exatamente as da constraint — é essa
# a forma que o Postgres consegue usar tanto na leitura pela relação quanto na checagem
# de integridade disparada por DELETE/UPDATE no lado pai.
FK_SEM_INDICE = text("""
    SELECT c.conrelid::regclass::text || ' (' ||
           string_agg(a.attname, ', ' ORDER BY k.ord) || ')'
    FROM pg_constraint c
    CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord)
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
    WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
      AND NOT EXISTS (
        SELECT 1 FROM pg_index i
        WHERE i.indrelid = c.conrelid
          AND (i.indkey::smallint[])[0:array_length(c.conkey, 1) - 1] = c.conkey
      )
    GROUP BY c.oid, c.conrelid
    ORDER BY 1
    """)


def _arquivos_de_producao() -> list[Path]:
    return sorted(p for p in APP.rglob("*.py") if "__pycache__" not in p.parts)


def _codigo_de(caminho: Path) -> list[tuple[int, str]]:
    """Linhas de CÓDIGO do arquivo, sem docstring e sem comentário.

    Varrer o texto cru transformaria a própria explicação de por que não se usa `OFFSET`
    numa violação de "não use OFFSET" — foi o que aconteceu ao escrever este teste. A
    AST resolve de vez: comentário nem chega nela, e docstring é o único `Expr` de
    string solto, fácil de reconhecer e descartar.
    """
    arvore = ast.parse(caminho.read_text())
    docstrings = {
        # O id do nó `Constant`, não o do `Expr` que o envolve: é o `Constant` que a
        # varredura abaixo encontra.
        id(no.body[0].value)
        for no in ast.walk(arvore)
        if isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and no.body
        and isinstance(no.body[0], ast.Expr)
        and isinstance(no.body[0].value, ast.Constant)
        and isinstance(no.body[0].value.value, str)
    }
    trechos: list[tuple[int, str]] = []
    for no in ast.walk(arvore):
        if id(no) in docstrings:
            continue
        if isinstance(no, ast.Constant) and isinstance(no.value, str):
            trechos.append((no.lineno, no.value))
        elif isinstance(no, ast.Attribute):
            trechos.append((no.lineno, f".{no.attr}("))
    return trechos


async def test_toda_fk_tem_indice(admin_engine: AsyncEngine) -> None:
    """Regra 4.

    FK sem índice cobra em dois lugares, e o segundo é o que pega de surpresa: além de
    a leitura pela relação virar Seq Scan, TODO `DELETE` no lado pai varre a tabela
    filha inteira, uma vez por linha, para checar a integridade. É o que transforma
    "excluir um cliente" em trinta segundos de banco travado quando o volume chega.
    """
    async with admin_engine.begin() as conn:
        descobertas = list((await conn.execute(FK_SEM_INDICE)).scalars().all())

    assert descobertas == [], (
        "chaves estrangeiras sem índice que as cubra (regra 4) — crie os índices numa "
        "migration:\n  " + "\n  ".join(descobertas)
    )


def test_nenhuma_listagem_usa_offset() -> None:
    """Regra 3: keyset em toda listagem.

    `OFFSET n` obriga o Postgres a produzir e DESCARTAR as n primeiras linhas. A página
    1 é instantânea, a 500 varre meio milhão de linhas para devolver vinte — e a
    degradação é invisível em desenvolvimento, onde ninguém chega à página 500.
    """
    ofensores = [
        f"{caminho.relative_to(APP.parent)}:{numero}"
        for caminho in _arquivos_de_producao()
        for numero, trecho in _codigo_de(caminho)
        if re.search(r"\.offset\(", trecho) or re.search(r"\bOFFSET\b", trecho)
    ]

    assert ofensores == [], "listagem com OFFSET (regra 3); use keyset:\n  " + "\n  ".join(
        ofensores
    )


def test_nenhum_select_estrela_em_codigo_de_producao() -> None:
    """Regra 5.

    O ORM já monta a lista de colunas sozinho — o risco é a SQL crua em `text()`.
    `SELECT *` traz colunas que ninguém pediu (inclusive `TEXT` grande e `tsvector`
    gerado) e, pior, muda de forma sozinho quando alguém adiciona uma coluna.

    `SELECT * FROM funcao(...)` fica de fora: a assinatura da função SQL É a lista de
    colunas e não muda quando alguém adiciona coluna numa tabela. É assim que as três
    funções `SECURITY DEFINER` da 079 e a `api_token_lookup` da 095 são lidas, e trocar
    o `*` por uma lista ali só criaria duas listas para manter em sincronia.
    """
    ofensores = [
        f"{caminho.relative_to(APP.parent)}:{numero}"
        for caminho in _arquivos_de_producao()
        for numero, trecho in _codigo_de(caminho)
        if re.search(r"SELECT\s+\*", trecho, re.IGNORECASE)
        and not re.search(r"SELECT\s+\*\s+FROM\s+\w+\s*\(", trecho, re.IGNORECASE)
    ]

    assert ofensores == [], "SELECT * em código de produção (regra 5):\n  " + "\n  ".join(ofensores)


@pytest.mark.parametrize("consultas", [0, 1, 5])
def test_contador_do_orcamento_conta_o_que_promete(consultas: int) -> None:
    """O gate depende de o instrumento estar certo. Um contador que devolvesse sempre
    zero deixaria todo orçamento passar e ninguém notaria — o teste do teste existe
    porque a falha dele é silenciosa."""
    from tests.perf import QueryLog

    log = QueryLog()
    for i in range(consultas):
        log.statements.append(f"SELECT {i}")

    assert log.count == consultas


def test_contador_ignora_o_preambulo_de_rls() -> None:
    """`SELECT set_config('app.tenant_id', ...)` é plumbing de sessão, não acesso a dado.
    Contá-lo faria o orçamento medir a quantidade de sessões abertas e mudar junto com
    refatorações que não tocam em query nenhuma."""
    from tests.perf import _PREAMBULO

    assert _PREAMBULO.match("SELECT set_config('app.tenant_id', $1::VARCHAR, true)")
    assert not _PREAMBULO.match("SELECT customers.id FROM customers")

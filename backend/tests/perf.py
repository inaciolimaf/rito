"""Instrumento de orçamento de queries (spec 098, §5 e regras 1 e 11).

O gate de performance que roda em TODO PR não mede tempo — mede **número de queries**.
Tempo em máquina de CI compartilhada oscila 30% entre execuções e transforma o gate em
gerador de falso vermelho; contagem de queries é determinística, e é ela que pega a
regressão que interessa: o N+1 que alguém acabou de introduzir sem perceber.

## Por que um gerenciador de contexto e não o decorador do §5 da spec

A spec desenhou `@assert_query_budget(max_queries=5)` sobre a função de teste inteira.
Não sobrevive ao contato: o teste precisa **montar** o cenário (criar escritório,
processo, lançamentos) antes de medir, e essa montagem são dezenas de queries. Um
decorador que abrace a função inteira ou conta o setup — e aí o orçamento não significa
nada — ou exige que todo setup vá para fixture, o que empurra a complexidade para outro
lugar sem resolvê-la. O gerenciador de contexto delimita exatamente a requisição medida.
"""

import contextlib
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from fastapi import FastAPI
from sqlalchemy import event

# `SELECT set_config('app.tenant_id', ...)` é o preâmbulo de RLS que TODA sessão emite
# (spec 003) — plumbing de sessão, não acesso a dado. Contá-lo faria o orçamento medir a
# quantidade de sessões abertas em vez do trabalho do endpoint, e mudaria junto com uma
# refatoração que não tocasse em query nenhuma.
# Idem para o `SAVEPOINT`/`RELEASE`/`ROLLBACK TO` que a spec 105 introduziu: dentro da
# suíte, a transação de quem chamou é a do TESTE, e cada sessão da aplicação entra nela
# por savepoint. São instruções de isolamento de teste, não trabalho do endpoint — em
# produção elas não existem, e contá-las mediria a fixture em vez da rota.
_PREAMBULO = re.compile(
    r"^\s*(?:SELECT\s+set_config\(|SAVEPOINT\b|RELEASE\s+SAVEPOINT\b|ROLLBACK\s+TO\b)",
    re.IGNORECASE,
)


def e_plumbing(statement: str) -> bool:
    """`True` para instrução de infraestrutura de sessão, que nenhum orçamento conta.

    Seis testes repetiam `if "set_config" not in statement` à mão (regra dos 3 usos do
    CLAUDE.md §6, com folga) e nenhum deles sabia dos savepoints da 105 — por isso o
    predicado passou a morar aqui, uma vez só.
    """
    return bool(_PREAMBULO.match(statement))


@dataclass
class QueryLog:
    statements: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.statements)

    def resumo(self) -> str:
        """Uma linha por query, cortada — o que se lê quando o orçamento estoura."""
        return "\n".join(f"  {i + 1}. {s.strip()[:160]}" for i, s in enumerate(self.statements))


@contextlib.asynccontextmanager
async def count_queries(app: FastAPI) -> AsyncIterator[QueryLog]:
    """Conta as queries emitidas pelo app dentro do bloco.

    O listener é atado ao engine da aplicação, e não ao da fixture de teste: é o engine
    da aplicação que atende as requisições, e um endpoint que abrisse conexão própria
    (bug de SRP) apareceria como zero query em vez de passar despercebido.
    """
    log = QueryLog()

    def _registrar(conn, cursor, statement, parameters, context, executemany) -> None:  # type: ignore[no-untyped-def]
        if not e_plumbing(statement):
            log.statements.append(statement)

    engine = app.state.engine.sync_engine
    event.listen(engine, "before_cursor_execute", _registrar)
    try:
        yield log
    finally:
        event.remove(engine, "before_cursor_execute", _registrar)


@contextlib.asynccontextmanager
async def query_budget(app: FastAPI, max_queries: int, *, label: str) -> AsyncIterator[QueryLog]:
    """Falha se o bloco emitir mais que `max_queries` queries.

    A mensagem lista as queries emitidas: um orçamento estourado sem a lista obriga quem
    quebrou a reproduzir localmente para descobrir o quê, e o gate vira burocracia.
    """
    async with count_queries(app) as log:
        yield log
    assert log.count <= max_queries, (
        f"{label}: {log.count} queries, orçamento é {max_queries} (spec 098, regra 1)\n"
        f"{log.resumo()}"
    )

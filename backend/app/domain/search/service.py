"""Busca global (spec 096).

Uma consulta por faceta, todas com o RLS da sessão — o isolamento não é reimplementado
aqui, é herdado. O que este service acrescenta é o RANKING, e ele tem uma ordem
deliberada (regra 4):

1. **correspondência exata primeiro**. Quem digita um CPF inteiro não quer relevância
   textual, quer aquela pessoa;
2. depois `ts_rank`, a relevância do Postgres;
3. depois recência, como desempate — entre dois resultados igualmente relevantes, o mais
   recente é quase sempre o que se procura.

A tarefa entra na busca sem `tsvector` próprio: ela não tem texto seu (o título vem do
tipo de tarefa), então a busca de tarefa é por processo e comentário, com `ILIKE`. Criar
uma terceira coluna gerada para ganhar pouco seria pagar em escrita o que não se ganha em
leitura.
"""

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import (
    ColumnElement,
    Select,
    delete,
    desc,
    func,
    literal,
    literal_column,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.customers.models import Customer
from app.domain.lawsuits.models import Lawsuit
from app.domain.posts.models import Post, PostUser
from app.domain.search.models import SearchHistory
from app.domain.search.query import ParsedQuery, QueryKind, parse_query, to_tsquery_input
from app.domain.task_types.models import TaskType
from app.domain.users.models import User

# Regra 5: dez por faceta na resposta rápida. "Ver todos" leva para a listagem, que tem
# filtro, ordenação e paginação de verdade.
MAX_PER_FACET = 10
# Regra 9.
MAX_HISTORY = 20


@dataclass
class SearchHit:
    id: uuid.UUID
    label: str
    sublabel: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class FacetResult:
    items: list[SearchHit]
    total: int


@dataclass
class SearchResults:
    people: FacetResult
    lawsuits: FacetResult
    tasks: FacetResult
    took_ms: int
    parsed_kind: str
    recent: list[str] = field(default_factory=list)


def _people_criteria(parsed: ParsedQuery) -> tuple[Any, Any, Any]:
    """Condição, ordem e o sinal de «casou exato» para a faceta de pessoas.

    Documento é comparação de dígitos com dígitos; o resto é busca textual. Regra 4: o
    exato vem antes do parcial — quem digitou o nome inteiro não quer ver mais ninguém na
    frente, e é esse booleano que a ordenação usa como primeira chave.
    """
    if parsed.kind is QueryKind.DOCUMENT:
        return Customer.identification == parsed.digits, desc(Customer.created_at), literal(False)
    consulta = to_tsquery_input(parsed.raw)
    vetor = literal_column("customers.search_vector", type_=TSVECTOR)
    tsquery = func.to_tsquery("portuguese", func.rito_unaccent(consulta))
    exato = func.coalesce(
        func.nullif(
            func.lower(func.rito_unaccent(Customer.name))
            == func.lower(func.rito_unaccent(parsed.raw)),
            False,
        ),
        False,
    )
    return vetor.op("@@")(tsquery), desc(func.ts_rank(vetor, tsquery)), exato


def _lawsuit_criteria(parsed: ParsedQuery) -> tuple[Any, Any] | None:
    """Condição e ordem da faceta de processos. `None` = não há o que buscar aqui.

    CPF não é número de processo, então documento devolve `None` em vez de ruído.

    Spec 098, regra 1: UNIÃO, não `OR`. `WHERE search_vector @@ ... OR folder ILIKE ...`
    obriga o Postgres a Seq Scan — são dois índices diferentes (GIN de texto e GIN
    trigrama) e ele não combina índices distintos dentro de um `OR`. Medido: 187 ms
    varrendo 101.504 processos para devolver zero. Como união de dois `SELECT id`, cada
    ramo usa o seu índice.
    """
    if parsed.kind is QueryKind.PROCESS_NUMBER:
        # Regra 2: CNJ com ou sem máscara. A coluna guarda só dígitos (spec 025).
        return Lawsuit.process_number == parsed.digits, desc(Lawsuit.created_at)
    if parsed.kind is QueryKind.DOCUMENT:
        return None
    consulta = to_tsquery_input(parsed.raw)
    vetor = literal_column("lawsuits.search_vector", type_=TSVECTOR)
    tsquery = func.to_tsquery("portuguese", func.rito_unaccent(consulta))
    por_texto = select(Lawsuit.id).where(vetor.op("@@")(tsquery))
    por_pasta = select(Lawsuit.id).where(Lawsuit.folder.ilike(f"%{parsed.raw}%"))
    condicao = Lawsuit.id.in_(por_texto.union(por_pasta).subquery().select())
    return condicao, desc(func.ts_rank(vetor, tsquery))


def _involved(user: User) -> ColumnElement[bool]:
    """Regra 6: tarefa privada só aparece para quem está envolvido nela.

    Mesma regra de `visibility.is_involved` (spec 033), aqui escrita como PREDICADO SQL:
    filtrar em Python exigiria carregar a base inteira para depois cortar dez linhas, e a
    busca global tem orçamento de 4 queries (CLAUDE.md §11).

    Envolvido é quem criou ou é responsável. O `EXISTS` correlacionado é o que evita
    multiplicar a linha da tarefa por responsável, como um JOIN faria.
    """
    return or_(
        Post.is_private.is_(False),
        Post.created_by == user.id,
        select(literal(1)).where(PostUser.post_id == Post.id, PostUser.user_id == user.id).exists(),
    )


class SearchService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def search(
        self, raw_query: str, *, user: User, facet: str = "all", limit: int = MAX_PER_FACET
    ) -> SearchResults:
        comeco = time.perf_counter()
        parsed = parse_query(raw_query)
        limite = min(limit, MAX_PER_FACET)
        vazio = FacetResult(items=[], total=0)

        if parsed.kind is QueryKind.TOO_SHORT:
            # Regra 12: busca curta devolve as recentes, não um erro.
            return SearchResults(
                people=vazio,
                lawsuits=vazio,
                tasks=vazio,
                took_ms=_elapsed(comeco),
                parsed_kind=parsed.kind.value,
                recent=await self.recent(user_id=user.id),
            )

        quer_pessoas = facet in ("all", "people")
        quer_processos = facet in ("all", "lawsuits")
        quer_tarefas = facet == "all"

        return SearchResults(
            people=await self._people(parsed, limite) if quer_pessoas else vazio,
            lawsuits=await self._lawsuits(parsed, limite) if quer_processos else vazio,
            tasks=await self._tasks(parsed, user, limite) if quer_tarefas else vazio,
            took_ms=_elapsed(comeco),
            parsed_kind=parsed.kind.value,
        )

    # ------------------------------------------------------------------ facetas

    async def _people(self, parsed: ParsedQuery, limit: int) -> FacetResult:
        if parsed.kind is QueryKind.PROCESS_NUMBER:
            # Número de processo não é gente. Devolver "nenhuma pessoa" é mais honesto
            # que devolver ruído textual.
            return FacetResult(items=[], total=0)

        condicao, ordem, exato = _people_criteria(parsed)

        stmt: Select[Any] = (
            select(Customer, exato.label("exato"), _facet_total())
            .where(condicao, Customer.is_archived.is_(False))
            .order_by(desc(literal_column("exato")), ordem, desc(Customer.created_at))
            .limit(limit)
        )
        linhas = (await self.session.execute(stmt)).all()
        total = _total_de(linhas)
        return FacetResult(
            items=[
                SearchHit(
                    id=row[0].id,
                    label=row[0].name,
                    sublabel=row[0].identification or row[0].email,
                    extra={"type": row[0].type.value},
                )
                for row in linhas
            ],
            total=total,
        )

    async def _lawsuits(self, parsed: ParsedQuery, limit: int) -> FacetResult:
        criterio = _lawsuit_criteria(parsed)
        if criterio is None:
            return FacetResult(items=[], total=0)
        condicao, ordem = criterio

        stmt = (
            select(Lawsuit, _facet_total())
            .where(condicao)
            .order_by(ordem, desc(Lawsuit.created_at))
            .limit(limit)
        )
        linhas = (await self.session.execute(stmt)).all()
        return FacetResult(
            items=[
                SearchHit(
                    id=row[0].id,
                    label=row[0].process_number or row[0].folder or "Processo sem número",
                    sublabel=row[0].county or row[0].folder,
                    extra={"folder": row[0].folder},
                )
                for row in linhas
            ],
            total=_total_de(linhas),
        )

    async def _tasks(self, parsed: ParsedQuery, user: User, limit: int) -> FacetResult:
        if parsed.is_exact:
            return FacetResult(items=[], total=0)
        padrao = f"%{parsed.raw}%"
        stmt = (
            select(Post, TaskType.name, _facet_total())
            .join(TaskType, TaskType.id == Post.task_type_id)
            .where(
                or_(Post.comments.ilike(padrao), Post.location.ilike(padrao)),
                _involved(user),
            )
            .order_by(desc(Post.created_at))
            .limit(limit)
        )
        linhas = (await self.session.execute(stmt)).all()
        return FacetResult(
            items=[
                SearchHit(
                    id=row[0].id,
                    label=row[1],
                    sublabel=row[0].comments,
                    extra={"lawsuit_id": str(row[0].lawsuit_id)},
                )
                for row in linhas
            ],
            total=_total_de(linhas),
        )

    # ---------------------------------------------------------------- histórico

    async def recent(self, *, user_id: uuid.UUID, limit: int = 5) -> list[str]:
        stmt = (
            select(SearchHistory.query)
            .where(SearchHistory.user_id == user_id)
            .order_by(desc(SearchHistory.created_at))
            .limit(MAX_HISTORY)
        )
        vistos: list[str] = []
        for consulta in (await self.session.scalars(stmt)).all():
            # A mesma busca repetida três vezes ocupa três linhas do histórico e uma só
            # da lista — o que a pessoa quer ver são as últimas COISAS buscadas.
            if consulta not in vistos:
                vistos.append(consulta)
            if len(vistos) >= limit:
                break
        return vistos

    async def record_click(
        self,
        *,
        user_id: uuid.UUID,
        query: str,
        clicked_type: str | None,
        clicked_id: uuid.UUID | None,
    ) -> SearchHistory:
        """Regra 8: o clique é o sinal que interessa — a busca sem clique não achou nada
        que servisse, e guardar as duas coisas juntas é o que permite melhorar a ordem
        depois."""
        registro = SearchHistory(
            tenant_id=self.tenant_id,
            user_id=user_id,
            query=query.strip(),
            clicked_type=clicked_type,
            clicked_id=clicked_id,
        )
        self.session.add(registro)
        await self.session.flush()
        await self._trim_history(user_id)
        return registro

    async def _trim_history(self, user_id: uuid.UUID) -> None:
        """Regra 9 da 096: 20 por usuário. Histórico é atalho, não arquivo.

        Spec 098, regra 3: era um `OFFSET 20` para listar os excedentes e um `DELETE`
        para apagá-los. Virou uma query só — "apague o que não está entre os 20 mais
        recentes" — com `LIMIT` no lugar do `OFFSET`. O ganho aqui não é volume (são 20
        linhas), é não deixar um `OFFSET` no código para servir de exemplo ao próximo
        que precisar paginar.
        """
        manter = (
            select(SearchHistory.id)
            .where(SearchHistory.user_id == user_id)
            .order_by(desc(SearchHistory.created_at))
            .limit(MAX_HISTORY)
            .scalar_subquery()
        )
        await self.session.execute(
            delete(SearchHistory).where(
                SearchHistory.user_id == user_id,
                SearchHistory.id.not_in(manter),
            )
        )


def _elapsed(comeco: float) -> int:
    return int((time.perf_counter() - comeco) * 1000)


def _facet_total() -> Any:
    """Total de resultados da faceta, por função de janela (spec 098, regra 1).

    Cada faceta fazia duas queries — a página e um `SELECT count(*)` com os mesmos
    predicados. Três facetas, seis queries, mais a autenticação: a busca global custava
    7 contra um orçamento de 4. A janela é avaliada DEPOIS do `WHERE` e ANTES do
    `LIMIT`, então o número é o mesmo que o `count` separado produzia — com um plano em
    vez de dois.
    """
    return func.count().over().label("total")


def _total_de(linhas: Sequence[Any]) -> int:
    """Sem linhas não há janela para ler, e zero é o total correto."""
    return int(linhas[0].total) if linhas else 0

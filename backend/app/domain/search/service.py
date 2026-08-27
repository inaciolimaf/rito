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
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Select, desc, func, literal, literal_column, or_, select
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

        exato: Any = literal(False)
        if parsed.kind is QueryKind.DOCUMENT:
            condicao = Customer.identification == parsed.digits
            ordem: Any = desc(Customer.created_at)
        else:
            consulta = to_tsquery_input(parsed.raw)
            vetor = literal_column("customers.search_vector", type_=TSVECTOR)
            tsquery = func.to_tsquery("portuguese", func.rito_unaccent(consulta))
            condicao = vetor.op("@@")(tsquery)
            # Regra 4: exato antes de parcial. `name` igual ao termo é o caso em que a
            # pessoa digitou o nome inteiro — e aí ela não quer ver mais ninguém antes.
            exato = func.coalesce(
                func.nullif(
                    func.lower(func.rito_unaccent(Customer.name))
                    == func.lower(func.rito_unaccent(parsed.raw)),
                    False,
                ),
                False,
            )
            ordem = desc(func.ts_rank(vetor, tsquery))

        stmt: Select[Any] = (
            select(Customer, exato.label("exato"))
            .where(condicao, Customer.is_archived.is_(False))
            .order_by(desc(literal_column("exato")), ordem, desc(Customer.created_at))
            .limit(limit)
        )
        linhas = (await self.session.execute(stmt)).all()
        total = await self._count(Customer, condicao, Customer.is_archived.is_(False))
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
        if parsed.kind is QueryKind.PROCESS_NUMBER:
            # Regra 2: CNJ com ou sem máscara. A coluna guarda só dígitos (spec 025), e é
            # por isso que a busca compara dígitos com dígitos.
            condicao = Lawsuit.process_number == parsed.digits
            ordem: Any = desc(Lawsuit.created_at)
        elif parsed.kind is QueryKind.DOCUMENT:
            return FacetResult(items=[], total=0)
        else:
            consulta = to_tsquery_input(parsed.raw)
            vetor = literal_column("lawsuits.search_vector", type_=TSVECTOR)
            tsquery = func.to_tsquery("portuguese", func.rito_unaccent(consulta))
            condicao = or_(vetor.op("@@")(tsquery), Lawsuit.folder.ilike(f"%{parsed.raw}%"))
            ordem = desc(func.ts_rank(vetor, tsquery))

        stmt = (
            select(Lawsuit).where(condicao).order_by(ordem, desc(Lawsuit.created_at)).limit(limit)
        )
        linhas = list((await self.session.scalars(stmt)).all())
        return FacetResult(
            items=[
                SearchHit(
                    id=item.id,
                    label=item.process_number or item.folder or "Processo sem número",
                    sublabel=item.county or item.folder,
                    extra={"folder": item.folder},
                )
                for item in linhas
            ],
            total=await self._count(Lawsuit, condicao),
        )

    async def _tasks(self, parsed: ParsedQuery, user: User, limit: int) -> FacetResult:
        if parsed.is_exact:
            return FacetResult(items=[], total=0)
        padrao = f"%{parsed.raw}%"
        # Regra 6: tarefa privada só aparece para quem está envolvido. A regra é a mesma
        # de `visibility.is_involved` (spec 033), aqui escrita como predicado SQL porque
        # filtrar em Python exigiria carregar a base inteira antes de cortar dez.
        envolvido = or_(
            Post.is_private.is_(False),
            Post.created_by == user.id,
            select(literal(1))
            .where(PostUser.post_id == Post.id, PostUser.user_id == user.id)
            .exists(),
        )
        condicao = or_(Post.comments.ilike(padrao), Post.location.ilike(padrao))
        stmt = (
            select(Post, TaskType.name)
            .join(TaskType, TaskType.id == Post.task_type_id)
            .where(condicao, envolvido)
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
            total=await self._count(Post, condicao, envolvido),
        )

    async def _count(self, model: Any, *conditions: Any) -> int:
        stmt = select(func.count()).select_from(model)
        for condicao in conditions:
            stmt = stmt.where(condicao)
        return int((await self.session.execute(stmt)).scalar_one())

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
        """Regra 9: 20 por usuário. Histórico é atalho, não arquivo."""
        stmt = (
            select(SearchHistory.id)
            .where(SearchHistory.user_id == user_id)
            .order_by(desc(SearchHistory.created_at))
            .offset(MAX_HISTORY)
        )
        excedentes = list((await self.session.scalars(stmt)).all())
        if not excedentes:
            return
        from sqlalchemy import delete

        await self.session.execute(delete(SearchHistory).where(SearchHistory.id.in_(excedentes)))


def _elapsed(comeco: float) -> int:
    return int((time.perf_counter() - comeco) * 1000)

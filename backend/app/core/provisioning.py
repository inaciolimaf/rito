"""Seed global e provisionamento de escritório (spec 099, regras 7 e 8).

Duas operações com naturezas opostas, e a distinção é a mesma da RLS:

- **catálogo global** (regra 7) — tribunais, sistemas, cargos, fases, grupos do DRE,
  agentes de petição: iguais para todo mundo, sem `tenant_id`. Semeado pelas migrations
  e **reafirmado no boot**, de forma idempotente. Reafirmar não é redundância: uma linha
  global pode desaparecer sem ninguém notar (foi o que aconteceu com os 19 agentes da
  087, levados por um `TRUNCATE ... CASCADE` de script de teste), e a migration que a
  criou não roda de novo porque já está aplicada.
- **taxonomia do escritório** (regra 8) — grupos de ação, etapas, tipos de tarefa,
  origens, categorias financeiras: por `tenant_id`, com RLS. Criada **na criação do
  tenant**, e só nela.

Até a 099 a segunda não existia. As migrations 014/015/016/031/054 semearam a taxonomia
para os tenants que existiam quando rodaram — cada uma anotou a limitação no comentário —
e um escritório criado depois nascia sem grupo de ação, sem etapa e sem tipo de tarefa,
isto é, incapaz de cadastrar um processo.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    Boolean,
    ColumnElement,
    Integer,
    Text,
    and_,
    cast,
    exists,
    literal,
    select,
)
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.dialects.postgresql import ENUM as PGENUM
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.functions import func

from app.core import tenant_catalog
from app.domain.action_groups.models import ActionGroup, LawsuitType
from app.domain.customer_origins.models import CustomerOrigin
from app.domain.financial.models import CostCenter, EntryType, FinancialCategory
from app.domain.legal_agents.catalog import AGENT_SEEDS
from app.domain.legal_agents.models import LegalAgent
from app.domain.stages.models import Stage, Step
from app.domain.task_types.models import TaskType

logger = logging.getLogger("rito.provisioning")

# `entry_type` já existe no banco (migration 054) — este é só o tipo do CAST.
_ENTRY_TYPE = PGENUM(EntryType, name="entry_type", create_type=False)


@dataclass(frozen=True)
class SeedResult:
    """Quantas linhas cada catálogo ganhou. Zero em tudo é o caso normal — significa que
    já estava tudo lá, que é justamente o que "idempotente" quer dizer."""

    legal_agents: int = 0

    @property
    def total(self) -> int:
        return self.legal_agents


def _tenant(tenant_id: uuid.UUID) -> ColumnElement[uuid.UUID]:
    """O `tenant_id` como parâmetro ligado e TIPADO.

    O tipo é obrigatório: sem ele o asyncpg recebe um UUID cru para uma coluna `uuid` e
    não tem como inferir o tipo do parâmetro dentro de um `INSERT ... SELECT`, onde não
    existe coluna de destino para guiá-lo.
    """
    return literal(tenant_id, PGUUID(as_uuid=True))


def _sem_acento(nome: InstrumentedAttribute[str]) -> ColumnElement[str]:
    """`immutable_unaccent(lower(name))` — a expressão dos índices únicos de taxonomia
    (spec 102), e portanto o alvo de todo `ON CONFLICT` daqui."""
    return func.immutable_unaccent(func.lower(nome))


async def seed_global_catalogs(conn: AsyncConnection) -> SeedResult:
    """Regra 7: idempotente, roda no boot.

    Só repõe o que uma migration semeou e que pode ter sumido — hoje, os agentes de
    sistema. Tribunais, cidades, cargos e fases não têm caminho conhecido de perda (não
    referenciam `tenants`, então nenhum `CASCADE` os alcança) e não entram aqui: um seed
    que reescreve tudo a cada boot custa tempo de arranque e esconde perda em vez de
    denunciá-la.
    """
    inseridos = 0
    for seed in AGENT_SEEDS:
        prompt = seed.system_prompt()
        ja_existe = exists(
            select(literal(1)).where(LegalAgent.tenant_id.is_(None), LegalAgent.code == seed.code)
        )
        resultado = await conn.execute(
            insert(LegalAgent).from_select(
                ["code", "name", "practice_area", "system_prompt", "original_system_prompt"],
                select(
                    literal(seed.code),
                    literal(seed.name),
                    literal(seed.practice_area),
                    literal(prompt),
                    literal(prompt),
                ).where(~ja_existe),
            )
        )
        inseridos += resultado.rowcount or 0
    if inseridos:
        logger.warning(
            "catálogo global reposto no boot", extra={"legal_agents_inseridos": inseridos}
        )
    return SeedResult(legal_agents=inseridos)


# Uma função por taxonomia (spec 121). Antes eram sete blocos no corpo de
# `provision_tenant`, 126 linhas seguidas — a maior função do backend. Cada uma devolve
# quantas linhas criou, e o `provision_tenant` virou a lista do que um escritório novo
# ganha, legível de uma vez.
#
# Todas são `ON CONFLICT DO NOTHING` (regra 8): rodar duas vezes não duplica, o que torna
# o provisionamento seguro de repetir quando morre no meio.
#
# Spec 115: os valores viajam como arrays LIGADOS via `unnest`, não interpolados no SQL.
# Nenhum vem de fora — são constantes de migration —, mas a forma da interpolação é a da
# injeção, e um apóstrofo num nome de taxonomia («Ação de Cobrança d'Água») quebraria a
# query.
#
# Spec 127: o `unnest` continua, agora montado pelo query builder — `func.unnest(...)
# .table_valued(...)` é a mesma coisa que `unnest(...) AS t(col, col)`, com a vantagem de
# que os nomes das colunas passam a ser identificadores Python que o `mypy` confere.


def _unnest(*colunas: tuple[str, Sequence[Any], Any]) -> Any:
    """`unnest(:a, :b) AS t(nome_a, nome_b)` — cada coluna é (nome, valores, tipo).

    `render_derived()` é o que faz o SQLAlchemy EMITIR a lista de colunas do alias. Sem
    ele o `.c.<nome>` existe do lado Python e o Postgres não conhece a coluna.
    """
    arrays = [literal(valores, ARRAY(tipo)) for _nome, valores, tipo in colunas]
    return func.unnest(*arrays).table_valued(*[nome for nome, _v, _t in colunas]).render_derived()


async def _seed_action_groups(conn: AsyncConnection, tenant_id: uuid.UUID) -> int:
    grupos = _unnest(("name", list(tenant_catalog.action_groups()), Text))
    resultado = await conn.execute(
        insert(ActionGroup)
        .from_select(["tenant_id", "name"], select(_tenant(tenant_id), grupos.c.name))
        .on_conflict_do_nothing(
            index_elements=[ActionGroup.tenant_id, _sem_acento(ActionGroup.name)]
        )
    )
    return resultado.rowcount or 0


async def _seed_lawsuit_types(conn: AsyncConnection, tenant_id: uuid.UUID) -> int:
    tipos = list(tenant_catalog.lawsuit_types())
    t = _unnest(
        ("type_name", [tipo for tipo, _grupo in tipos], Text),
        ("group_name", [grupo for _tipo, grupo in tipos], Text),
    )
    origem = (
        select(_tenant(tenant_id), ActionGroup.id, t.c.type_name)
        .select_from(t)
        .join(
            ActionGroup,
            and_(ActionGroup.tenant_id == _tenant(tenant_id), ActionGroup.name == t.c.group_name),
        )
    )
    resultado = await conn.execute(
        insert(LawsuitType)
        .from_select(["tenant_id", "action_group_id", "name"], origem)
        .on_conflict_do_nothing(
            index_elements=[LawsuitType.tenant_id, _sem_acento(LawsuitType.name)]
        )
    )
    return resultado.rowcount or 0


async def _seed_stages(conn: AsyncConnection, tenant_id: uuid.UUID) -> int:
    """`position` vem da ordem da lista: as 59 etapas têm ordem definida pela 015, e
    embaralhá-las mudaria o funil que o escritório vê na primeira abertura do CRM."""
    etapas = list(enumerate(tenant_catalog.stages(), start=1))
    e = _unnest(
        ("nome", [etapa for _pos, (etapa, _fase) in etapas], Text),
        ("fase", [fase for _pos, (_etapa, fase) in etapas], Text),
        ("posicao", [pos for pos, _ in etapas], Integer),
    )
    origem = (
        select(_tenant(tenant_id), Step.id, e.c.nome, e.c.posicao)
        .select_from(e)
        .join(Step, Step.name == e.c.fase)
    )
    resultado = await conn.execute(
        insert(Stage)
        .from_select(["tenant_id", "step_id", "name", "position"], origem)
        .on_conflict_do_nothing(
            index_elements=[Stage.tenant_id, Stage.step_id, _sem_acento(Stage.name)]
        )
    )
    return resultado.rowcount or 0


async def _seed_customer_origins(conn: AsyncConnection, tenant_id: uuid.UUID) -> int:
    origens = _unnest(("name", list(tenant_catalog.customer_origins()), Text))
    resultado = await conn.execute(
        insert(CustomerOrigin)
        .from_select(["tenant_id", "name"], select(_tenant(tenant_id), origens.c.name))
        .on_conflict_do_nothing(
            index_elements=[CustomerOrigin.tenant_id, _sem_acento(CustomerOrigin.name)]
        )
    )
    return resultado.rowcount or 0


async def _seed_task_types(conn: AsyncConnection, tenant_id: uuid.UUID) -> int:
    tarefas = list(tenant_catalog.task_types())
    t = _unnest(
        ("nome", [nome for nome, _p, _s in tarefas], Text),
        ("pontos", [pontos for _n, pontos, _s in tarefas], Integer),
        ("sistemica", [sistemica for _n, _p, sistemica in tarefas], Boolean),
    )
    origem = select(_tenant(tenant_id), t.c.nome, t.c.pontos, t.c.sistemica)
    resultado = await conn.execute(
        insert(TaskType)
        .from_select(["tenant_id", "name", "reward", "is_system"], origem)
        .on_conflict_do_nothing(index_elements=[TaskType.tenant_id, _sem_acento(TaskType.name)])
    )
    return resultado.rowcount or 0


async def _seed_financial_categories(conn: AsyncConnection, tenant_id: uuid.UUID) -> int:
    categorias = list(tenant_catalog.financial_categories())
    c = _unnest(
        ("nome", [nome for nome, _t, _g in categorias], Text),
        ("tipo", [tipo for _n, tipo, _g in categorias], Text),
        ("grupo", [grupo for _n, _t, grupo in categorias], Integer),
    )
    origem = select(
        _tenant(tenant_id), c.c.grupo, c.c.nome, cast(c.c.tipo, _ENTRY_TYPE), literal(True)
    )
    resultado = await conn.execute(
        insert(FinancialCategory)
        .from_select(["tenant_id", "dre_group_id", "name", "type", "is_default"], origem)
        .on_conflict_do_nothing(
            index_elements=[FinancialCategory.tenant_id, _sem_acento(FinancialCategory.name)]
        )
    )
    return resultado.rowcount or 0


async def _seed_default_cost_center(conn: AsyncConnection, tenant_id: uuid.UUID) -> int:
    """Um centro de custo padrão para o escritório poder lançar despesa no primeiro dia."""
    resultado = await conn.execute(
        insert(CostCenter)
        .values(tenant_id=tenant_id, name="GERAL", is_default=True)
        .on_conflict_do_nothing(index_elements=[CostCenter.tenant_id, _sem_acento(CostCenter.name)])
    )
    return resultado.rowcount or 0


async def provision_tenant(conn: AsyncConnection, tenant_id: uuid.UUID) -> dict[str, int]:
    """Regra 8: a taxonomia padrão do escritório novo.

    Roda com a conexão de superusuário (é criação de tenant, anterior a qualquer sessão
    de usuário), e todo `INSERT` é `ON CONFLICT DO NOTHING` — rodar duas vezes no mesmo
    escritório não duplica nada, o que torna a operação segura de repetir quando um
    provisionamento morre no meio.
    """
    return {
        "action_groups": await _seed_action_groups(conn, tenant_id),
        "lawsuit_types": await _seed_lawsuit_types(conn, tenant_id),
        "stages": await _seed_stages(conn, tenant_id),
        "customer_origins": await _seed_customer_origins(conn, tenant_id),
        "task_types": await _seed_task_types(conn, tenant_id),
        "financial_categories": await _seed_financial_categories(conn, tenant_id),
        "cost_centers": await _seed_default_cost_center(conn, tenant_id),
    }

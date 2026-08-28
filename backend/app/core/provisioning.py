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
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core import tenant_catalog
from app.domain.legal_agents.catalog import AGENT_SEEDS

logger = logging.getLogger("rito.provisioning")


@dataclass(frozen=True)
class SeedResult:
    """Quantas linhas cada catálogo ganhou. Zero em tudo é o caso normal — significa que
    já estava tudo lá, que é justamente o que "idempotente" quer dizer."""

    legal_agents: int = 0

    @property
    def total(self) -> int:
        return self.legal_agents


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
        resultado = await conn.execute(
            text("""
                INSERT INTO legal_agents
                    (code, name, practice_area, system_prompt, original_system_prompt)
                SELECT :code, :name, :area, :prompt, :prompt
                WHERE NOT EXISTS (
                    SELECT 1 FROM legal_agents
                     WHERE tenant_id IS NULL AND code = :code
                )
                """),
            {
                "code": seed.code,
                "name": seed.name,
                "area": seed.practice_area,
                "prompt": seed.system_prompt(),
            },
        )
        inseridos += resultado.rowcount or 0
    if inseridos:
        logger.warning(
            "catálogo global reposto no boot", extra={"legal_agents_inseridos": inseridos}
        )
    return SeedResult(legal_agents=inseridos)


async def provision_tenant(conn: AsyncConnection, tenant_id: uuid.UUID) -> dict[str, int]:
    """Regra 8: a taxonomia padrão do escritório novo.

    Roda com a conexão de superusuário (é criação de tenant, anterior a qualquer sessão
    de usuário), e todo `INSERT` é `ON CONFLICT DO NOTHING` — rodar duas vezes no mesmo
    escritório não duplica nada, o que torna a operação segura de repetir quando um
    provisionamento morre no meio.
    """
    parametros = {"tenant": tenant_id}
    criados: dict[str, int] = {}

    grupos = ", ".join(f"('{nome}')" for nome in tenant_catalog.action_groups())
    resultado = await conn.execute(
        text(f"""
            INSERT INTO action_groups (tenant_id, name)
            SELECT :tenant, g.name FROM (VALUES {grupos}) AS g(name)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        parametros,
    )
    criados["action_groups"] = resultado.rowcount or 0

    tipos = ", ".join(f"('{tipo}', '{grupo}')" for tipo, grupo in tenant_catalog.lawsuit_types())
    resultado = await conn.execute(
        text(f"""
            INSERT INTO lawsuit_types (tenant_id, action_group_id, name)
            SELECT :tenant, ag.id, t.type_name
            FROM (VALUES {tipos}) AS t(type_name, group_name)
            JOIN action_groups ag
              ON ag.tenant_id = :tenant AND ag.name = t.group_name
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        parametros,
    )
    criados["lawsuit_types"] = resultado.rowcount or 0

    # `position` vem da ordem da lista: as 59 etapas têm ordem definida pela 015, e
    # embaralhá-las mudaria o funil que o escritório vê na primeira abertura do CRM.
    etapas = ", ".join(
        f"('{etapa}', '{fase}', {posicao})"
        for posicao, (etapa, fase) in enumerate(tenant_catalog.stages(), start=1)
    )
    resultado = await conn.execute(
        text(f"""
            INSERT INTO stages (tenant_id, step_id, name, position)
            SELECT :tenant, s.id, e.nome, e.posicao
            FROM (VALUES {etapas}) AS e(nome, fase, posicao)
            JOIN steps s ON s.name = e.fase
            ON CONFLICT (tenant_id, step_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        parametros,
    )
    criados["stages"] = resultado.rowcount or 0

    origens = ", ".join(f"('{nome}')" for nome in tenant_catalog.customer_origins())
    resultado = await conn.execute(
        text(f"""
            INSERT INTO customer_origins (tenant_id, name)
            SELECT :tenant, o.name FROM (VALUES {origens}) AS o(name)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        parametros,
    )
    criados["customer_origins"] = resultado.rowcount or 0

    tarefas = ", ".join(
        f"('{nome}', {pontos}, {str(sistemica).lower()})"
        for nome, pontos, sistemica in tenant_catalog.task_types()
    )
    resultado = await conn.execute(
        text(f"""
            INSERT INTO task_types (tenant_id, name, reward, is_system)
            SELECT :tenant, t.nome, t.pontos, t.sistemica
            FROM (VALUES {tarefas}) AS t(nome, pontos, sistemica)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        parametros,
    )
    criados["task_types"] = resultado.rowcount or 0

    categorias = ", ".join(
        f"('{nome}', '{tipo}', {grupo})"
        for nome, tipo, grupo in tenant_catalog.financial_categories()
    )
    resultado = await conn.execute(
        text(f"""
            INSERT INTO financial_categories (tenant_id, dre_group_id, name, type, is_default)
            SELECT :tenant, c.grupo, c.nome, c.tipo::entry_type, true
            FROM (VALUES {categorias}) AS c(nome, tipo, grupo)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        parametros,
    )
    criados["financial_categories"] = resultado.rowcount or 0

    resultado = await conn.execute(
        text("""
            INSERT INTO cost_centers (tenant_id, name, is_default)
            VALUES (:tenant, 'GERAL', true)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        parametros,
    )
    criados["cost_centers"] = resultado.rowcount or 0

    return criados

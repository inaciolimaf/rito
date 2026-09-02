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
    criados: dict[str, int] = {}

    # Spec 115: as seis inserções montavam a lista `VALUES` interpolando os nomes do
    # catálogo direto no SQL, com aspas postas à mão (`f"('{nome}')"`). Nenhum valor vem
    # de fora — são constantes de uma migration —, mas a FORMA é a da injeção, e bastava
    # um apóstrofo num nome de taxonomia (`"Ação de Cobrança d'Água"`) para quebrar a
    # query. `unnest` de arrays LIGADOS faz o mesmo serviço sem construir SQL: o driver
    # manda os valores por fora do texto, e o problema deixa de existir em vez de ser
    # silenciado.
    grupos = list(tenant_catalog.action_groups())
    resultado = await conn.execute(
        text("""
            INSERT INTO action_groups (tenant_id, name)
            SELECT :tenant, g.name FROM unnest(CAST(:grupos AS text[])) AS g(name)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        {"tenant": tenant_id, "grupos": grupos},
    )
    criados["action_groups"] = resultado.rowcount or 0

    tipos = list(tenant_catalog.lawsuit_types())
    resultado = await conn.execute(
        text("""
            INSERT INTO lawsuit_types (tenant_id, action_group_id, name)
            SELECT :tenant, ag.id, t.type_name
            FROM unnest(CAST(:nomes AS text[]), CAST(:grupos AS text[]))
                 AS t(type_name, group_name)
            JOIN action_groups ag
              ON ag.tenant_id = :tenant AND ag.name = t.group_name
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        {
            "tenant": tenant_id,
            "nomes": [tipo for tipo, _grupo in tipos],
            "grupos": [grupo for _tipo, grupo in tipos],
        },
    )
    criados["lawsuit_types"] = resultado.rowcount or 0

    # `position` vem da ordem da lista: as 59 etapas têm ordem definida pela 015, e
    # embaralhá-las mudaria o funil que o escritório vê na primeira abertura do CRM.
    etapas = list(enumerate(tenant_catalog.stages(), start=1))
    resultado = await conn.execute(
        text("""
            INSERT INTO stages (tenant_id, step_id, name, position)
            SELECT :tenant, s.id, e.nome, e.posicao
            FROM unnest(
                     CAST(:nomes AS text[]),
                     CAST(:fases AS text[]),
                     CAST(:posicoes AS int[])
                 ) AS e(nome, fase, posicao)
            JOIN steps s ON s.name = e.fase
            ON CONFLICT (tenant_id, step_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        {
            "tenant": tenant_id,
            "nomes": [etapa for _pos, (etapa, _fase) in etapas],
            "fases": [fase for _pos, (_etapa, fase) in etapas],
            "posicoes": [pos for pos, _ in etapas],
        },
    )
    criados["stages"] = resultado.rowcount or 0

    resultado = await conn.execute(
        text("""
            INSERT INTO customer_origins (tenant_id, name)
            SELECT :tenant, o.name FROM unnest(CAST(:origens AS text[])) AS o(name)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        {"tenant": tenant_id, "origens": list(tenant_catalog.customer_origins())},
    )
    criados["customer_origins"] = resultado.rowcount or 0

    tarefas = list(tenant_catalog.task_types())
    resultado = await conn.execute(
        text("""
            INSERT INTO task_types (tenant_id, name, reward, is_system)
            SELECT :tenant, t.nome, t.pontos, t.sistemica
            FROM unnest(
                     CAST(:nomes AS text[]),
                     CAST(:pontos AS numeric[]),
                     CAST(:sistemicas AS boolean[])
                 ) AS t(nome, pontos, sistemica)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        {
            "tenant": tenant_id,
            "nomes": [nome for nome, _p, _s in tarefas],
            "pontos": [pontos for _n, pontos, _s in tarefas],
            "sistemicas": [sistemica for _n, _p, sistemica in tarefas],
        },
    )
    criados["task_types"] = resultado.rowcount or 0

    categorias = list(tenant_catalog.financial_categories())
    resultado = await conn.execute(
        text("""
            INSERT INTO financial_categories (tenant_id, dre_group_id, name, type, is_default)
            SELECT :tenant, c.grupo, c.nome, c.tipo::entry_type, true
            FROM unnest(
                     CAST(:nomes AS text[]),
                     CAST(:tipos AS text[]),
                     CAST(:grupos AS int[])
                 ) AS c(nome, tipo, grupo)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        {
            "tenant": tenant_id,
            "nomes": [nome for nome, _t, _g in categorias],
            "tipos": [tipo for _n, tipo, _g in categorias],
            "grupos": [grupo for _n, _t, grupo in categorias],
        },
    )
    criados["financial_categories"] = resultado.rowcount or 0

    resultado = await conn.execute(
        text("""
            INSERT INTO cost_centers (tenant_id, name, is_default)
            VALUES (:tenant, 'GERAL', true)
            ON CONFLICT (tenant_id, immutable_unaccent(lower(name))) DO NOTHING
            """),
        {"tenant": tenant_id},
    )
    criados["cost_centers"] = resultado.rowcount or 0

    return criados

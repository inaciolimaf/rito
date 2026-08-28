"""Seed de volume realista (spec 098, §4 e regra 10).

Serve a UMA pergunta que nenhum teste de unidade responde: o plano que o Postgres
escolhe muda com o volume. Com mil linhas ele varre a tabela e é rápido; com cem mil ele
precisa do índice, e é aí que a falta de um aparece. Rodar isto num banco pequeno não
prova nada — e por isso ele não roda no CI de PR (regra 10), só no noturno.

Escala do §4 da spec:

| Entidade       | Quantidade |
|----------------|-----------:|
| Contatos       |    100.000 |
| Processos      |    100.000 |
| Tarefas        |    500.000 |
| Lançamentos    |    200.000 |
| Publicações    |     50.000 |
| Movimentações  |  1.000.000 |

A geração é feita em SQL (`INSERT ... SELECT generate_series`), não em Python: dois
milhões de objetos ORM levariam mais de uma hora e mediriam a velocidade do SQLAlchemy,
não a do banco. Rodar duas vezes é seguro — o seed apaga o que semeou antes, pelo
`tenant_id` fixo.

    python scripts/volume_seed.py              # semeia
    python scripts/volume_seed.py --drop       # remove

Mora em `scripts/` e não em `app/` de propósito: usa a conexão de superusuário
(`MIGRATIONS_DATABASE_URL`), que fora dos workers é exatamente o que o teste de
isolamento da 080 proíbe no código da aplicação. É ferramenta de operação, não módulo
do sistema — e a distinção é a mesma que separa `alembic/` de `app/`.
"""

import asyncio
import sys
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.config import get_settings
from app.core.db import create_engine_from_url

# Tenant fixo: o seed precisa ser idempotente e removível, e um UUID sorteado a cada
# execução deixaria lixo acumulando no banco de perfilagem.
VOLUME_TENANT_ID = uuid.UUID("00000000-0000-4000-8000-0000000098ee")
VOLUME_TENANT_SLUG = "volume-098"

# Ids fixos da taxonomia rasa do escritório de perfilagem — fixos pelo mesmo motivo do
# tenant: o seed precisa ser removível sem deixar rastro.
_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000009801")
_GROUP_ID = uuid.UUID("00000000-0000-4000-8000-0000000098a1")
_TYPE_ID = uuid.UUID("00000000-0000-4000-8000-0000000098a2")
_STAGE_ID = uuid.UUID("00000000-0000-4000-8000-0000000098a3")
_TASK_TYPE_ID = uuid.UUID("00000000-0000-4000-8000-0000000098a4")
_ORIGIN_ID = uuid.UUID("00000000-0000-4000-8000-0000000098a5")
_CATEGORY_ID = uuid.UUID("00000000-0000-4000-8000-0000000098a6")
_COST_CENTER_ID = uuid.UUID("00000000-0000-4000-8000-0000000098a7")

ESCALA = {
    "customers": 100_000,
    "lawsuits": 100_000,
    "posts": 500_000,
    "transactions": 200_000,
    "publications": 50_000,
    "lawsuit_movements": 1_000_000,
}


async def _tenant(conn: AsyncConnection) -> None:
    await conn.execute(
        text(
            "INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Volume 098') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": VOLUME_TENANT_ID, "slug": VOLUME_TENANT_SLUG},
    )


async def semear(conn: AsyncConnection) -> dict[str, int]:
    """Popula o tenant de volume. Devolve o que foi inserido, por tabela.

    A ordem importa: cada tabela referencia a anterior, e as chaves são sorteadas com
    `%` sobre `generate_series` para a distribuição ser realista — mil processos com uma
    movimentação cada e um processo com um milhão dariam planos completamente
    diferentes, e o segundo não é o escritório de ninguém.
    """
    await _tenant(conn)
    parametros = {"tenant": VOLUME_TENANT_ID}
    inseridos: dict[str, int] = {}

    # Taxonomia mínima do escritório de perfilagem. É deliberadamente rasa — um grupo,
    # um tipo de ação, uma etapa, um tipo de tarefa: o que se está medindo é o plano das
    # tabelas GRANDES, e uma taxonomia rica só acrescentaria linhas que já são poucas.
    # Dez usuários, não um. A diferença não é cosmética: com todas as 200 mil linhas
    # penduradas num único `user_id`, o planejador escolhe percorrer o índice de usuário
    # e ler a tabela inteira — e o perfilamento passa a medir uma distribuição que
    # nenhum escritório tem. Descoberto ao rodar o noturno pela primeira vez.
    await conn.execute(
        text("""
            INSERT INTO users (id, tenant_id, email, password_hash, name, role,
                               financial_access, is_active)
            VALUES (:user, :tenant, 'volume@rito.test', 'x', 'Volume', 'GESTOR', 'FULL', true)
            """),
        parametros | {"user": _USER_ID},
    )
    await conn.execute(
        text("""
            INSERT INTO users (tenant_id, email, password_hash, name, role,
                               financial_access, is_active)
            SELECT :tenant, 'volume' || i || '@rito.test', 'x', 'Colega ' || i,
                   'COLABORADOR'::user_role, 'NONE'::financial_access, true
            FROM generate_series(1, 9) AS i
            """),
        parametros,
    )
    await conn.execute(
        text(
            "INSERT INTO action_groups (id, tenant_id, name) " "VALUES (:grupo, :tenant, 'Volume')"
        ),
        parametros | {"grupo": _GROUP_ID},
    )
    await conn.execute(
        text(
            "INSERT INTO lawsuit_types (id, tenant_id, action_group_id, name) "
            "VALUES (:tipo, :tenant, :grupo, 'Volume')"
        ),
        parametros | {"tipo": _TYPE_ID, "grupo": _GROUP_ID},
    )
    await conn.execute(
        text(
            "INSERT INTO stages (id, tenant_id, step_id, name, position) "
            "VALUES (:etapa, :tenant, 1, 'Volume', 1)"
        ),
        parametros | {"etapa": _STAGE_ID},
    )
    await conn.execute(
        text(
            "INSERT INTO task_types (id, tenant_id, name, reward) "
            "VALUES (:tarefa, :tenant, 'Volume', 5)"
        ),
        parametros | {"tarefa": _TASK_TYPE_ID},
    )
    await conn.execute(
        text(
            "INSERT INTO customer_origins (id, tenant_id, name) "
            "VALUES (:origem, :tenant, 'Volume')"
        ),
        parametros | {"origem": _ORIGIN_ID},
    )
    # `ck_tx_non_transfer_needs_category` (spec 056): lançamento que não é transferência
    # exige categoria. A categoria exige grupo do DRE — catálogo global, já semeado pela
    # migration 054.
    await conn.execute(
        text("""
            INSERT INTO financial_categories (id, tenant_id, dre_group_id, name, type)
            SELECT :categoria, :tenant, id, 'Volume', 'RECEITA'::entry_type
            FROM dre_groups ORDER BY id LIMIT 1
            """),
        parametros | {"categoria": _CATEGORY_ID},
    )
    await conn.execute(
        text(
            "INSERT INTO cost_centers (id, tenant_id, name) " "VALUES (:centro, :tenant, 'Volume')"
        ),
        parametros | {"centro": _COST_CENTER_ID},
    )
    # Vinte etapas: um Kanban de uma coluna só não exercita o agrupamento por fase.
    await conn.execute(
        text("""
            INSERT INTO stages (tenant_id, step_id, name, position)
            SELECT :tenant, (i % 9) + 1, 'Etapa ' || i, i
            FROM generate_series(2, 20) AS i
            """),
        parametros,
    )

    # Nomes VARIADOS, não "Contato 1..100000". A primeira versão do seed dava o mesmo
    # prefixo a todo mundo, e aí `q=Contato` casava os 100 mil — o perfilamento da busca
    # media ordenar a base inteira por relevância, que é um caso que não existe. Com 400
    # combinações de nome e sobrenome, um termo casa alguns milhares, como na vida real.
    await conn.execute(
        text("""
            INSERT INTO customers (tenant_id, origin_id, type, name, created_at)
            SELECT :tenant, :origem, 'PF',
                   (ARRAY['Ana','Bruno','Carla','Diego','Elisa','Fabio','Gisele',
                          'Heitor','Iara','Joao','Karina','Lucas','Marina','Nuno',
                          'Olivia','Paulo','Renata','Sergio','Tania','Vitor'])[(i % 20) + 1]
                   || ' ' ||
                   (ARRAY['Silva','Souza','Costa','Pereira','Almeida','Rocha','Lima',
                          'Carvalho','Gomes','Martins','Araujo','Barbosa','Ribeiro',
                          'Teixeira','Nunes','Moreira','Cardoso','Freitas','Correia',
                          'Dias'])[((i / 20) % 20) + 1]
                   || ' ' || i,
                   now() - (i % 900) * interval '1 day'
            FROM generate_series(1, :n) AS i
            """),
        parametros | {"origem": _ORIGIN_ID, "n": ESCALA["customers"]},
    )
    inseridos["customers"] = ESCALA["customers"]

    await conn.execute(
        text("""
            WITH u AS (
                SELECT array_agg(id ORDER BY email) AS ids
                FROM users WHERE tenant_id = :tenant
            ), e AS (
                SELECT array_agg(id ORDER BY position) AS ids
                FROM stages WHERE tenant_id = :tenant
            )
            INSERT INTO lawsuits (tenant_id, user_id, lawsuit_type_id, stage_id,
                                  folder, created_at)
            SELECT :tenant,
                   u.ids[(i % array_length(u.ids, 1)) + 1],
                   :tipo,
                   e.ids[(i % array_length(e.ids, 1)) + 1],
                   'PASTA-' || i,
                   now() - (i % 900) * interval '1 day'
            FROM generate_series(1, :n) AS i, u, e
            """),
        parametros | {"tipo": _TYPE_ID, "n": ESCALA["lawsuits"]},
    )
    inseridos["lawsuits"] = ESCALA["lawsuits"]

    # As chaves de usuário e etapa vêm de um array montado UMA vez (CTE `u`/`e`) e
    # indexado por módulo. A primeira versão usava uma subconsulta ordenada por linha,
    # que é uma subconsulta ordenada POR LINHA: passou de dez minutos sem terminar.
    # 5 tarefas por processo, 10 movimentações por processo: as tabelas filhas ficam com
    # a proporção que um escritório real tem, e é essa proporção que decide se o
    # planejador escolhe índice ou varredura no JOIN.
    await conn.execute(
        text("""
            INSERT INTO posts (tenant_id, lawsuit_id, task_type_id, created_by,
                               reward_snapshot, created_at)
            SELECT :tenant, l.id, :tarefa, :user, 5,
                   now() - (i % 365) * interval '1 day'
            FROM generate_series(1, :por_processo) AS i
            CROSS JOIN LATERAL (
                SELECT id FROM lawsuits WHERE tenant_id = :tenant
                ORDER BY created_at LIMIT :processos
            ) AS l
            """),
        parametros
        | {
            "tarefa": _TASK_TYPE_ID,
            "user": _USER_ID,
            "por_processo": ESCALA["posts"] // ESCALA["lawsuits"],
            "processos": ESCALA["lawsuits"],
        },
    )
    inseridos["posts"] = ESCALA["posts"]

    await conn.execute(
        text("""
            INSERT INTO lawsuit_movements (tenant_id, lawsuit_id, origin, occurred_at, title)
            SELECT :tenant, l.id, 'TRIBUNAL'::movement_origin,
                   now() - (i % 365) * interval '1 day', 'Movimento ' || i
            FROM generate_series(1, :por_processo) AS i
            CROSS JOIN LATERAL (
                SELECT id FROM lawsuits WHERE tenant_id = :tenant
                ORDER BY created_at LIMIT :processos
            ) AS l
            """),
        parametros
        | {
            "por_processo": ESCALA["lawsuit_movements"] // ESCALA["lawsuits"],
            "processos": ESCALA["lawsuits"],
        },
    )
    inseridos["lawsuit_movements"] = ESCALA["lawsuit_movements"]

    await conn.execute(
        text("""
            WITH u AS (
                SELECT array_agg(id ORDER BY email) AS ids
                FROM users WHERE tenant_id = :tenant
            )
            INSERT INTO transactions (tenant_id, kind, user_id, category_id,
                                      cost_center_id, amount, due_date, competence,
                                      created_at)
            SELECT :tenant,
                   (CASE WHEN i % 2 = 0 THEN 'RECEITA' ELSE 'DESPESA' END)::transaction_kind,
                   u.ids[(i % array_length(u.ids, 1)) + 1],
                   :categoria, :centro, 100 + (i % 5000),
                   current_date - (i % 900),
                   date_trunc('month', current_date - (i % 900))::date,
                   now() - (i % 900) * interval '1 day'
            FROM generate_series(1, :n) AS i, u
            """),
        parametros
        | {
            "categoria": _CATEGORY_ID,
            "centro": _COST_CENTER_ID,
            "n": ESCALA["transactions"],
        },
    )
    inseridos["transactions"] = ESCALA["transactions"]

    await conn.execute(
        text("""
            INSERT INTO publications (tenant_id, external_id, hash, availability_date,
                                      court_code, body, raw_payload, created_at)
            SELECT :tenant, i, md5(i::text), current_date - (i % 365),
                   'TJSP', 'Intimação número ' || i, '{}'::jsonb,
                   now() - (i % 365) * interval '1 day'
            FROM generate_series(1, :n) AS i
            """),
        parametros | {"n": ESCALA["publications"]},
    )
    inseridos["publications"] = ESCALA["publications"]

    # Sem ANALYZE o planejador continua com as estatísticas do banco vazio e escolhe o
    # plano errado — o perfilamento mediria uma decisão que a produção nunca toma.
    await conn.execute(text("ANALYZE"))
    return inseridos


async def remover(conn: AsyncConnection) -> None:
    """`TRUNCATE ... CASCADE` e não `DELETE`: as FKs do Rito são `NO ACTION`, então
    apagar o tenant pelo id esbarra em cada tabela filha. O `CASCADE` aqui é seguro
    porque o escritório de volume é descartável por construção — e as tabelas de
    catálogo global sem tenant são preservadas do mesmo jeito que em
    `scripts/run-tests.sh`."""
    await conn.execute(
        text("DELETE FROM lawsuit_movements WHERE tenant_id = :id"), {"id": VOLUME_TENANT_ID}
    )
    for tabela in (
        "posts",
        "transactions",
        "publications",
        "lawsuits",
        "customers",
        "stages",
        "task_types",
        "financial_categories",
        "cost_centers",
        "customer_origins",
        "lawsuit_types",
        "action_groups",
        "users",
    ):
        await conn.execute(
            text(f"DELETE FROM {tabela} WHERE tenant_id = :id"), {"id": VOLUME_TENANT_ID}
        )
    await conn.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": VOLUME_TENANT_ID})


async def _vacuum(engine: AsyncEngine) -> None:
    """`VACUUM (ANALYZE)` nas tabelas grandes depois de remover o volume.

    Apagar 1,95 milhão de linhas não devolve o espaço: as tuplas mortas continuam
    ocupando páginas, e uma varredura sobre 20 mil linhas vivas passa a ler as páginas
    de 100 mil. Descoberto ao fechar a 098 — o teste de p95 da busca (spec 096, que semeia
    20 mil contatos próprios) passou a falhar DEPOIS de o volume ser removido, e o
    culpado era o inchaço, não a consulta.

    `VACUUM` não roda dentro de transação; daí a conexão em AUTOCOMMIT.
    """
    tabelas = (
        "lawsuit_movements",
        "posts",
        "transactions",
        "publications",
        "lawsuits",
        "customers",
    )
    async with engine.connect() as conn:
        conexao = await conn.execution_options(isolation_level="AUTOCOMMIT")
        for tabela in tabelas:
            await conexao.execute(text(f"VACUUM (ANALYZE) {tabela}"))


async def main() -> None:
    url = get_settings().migrations_database_url
    assert url is not None, "MIGRATIONS_DATABASE_URL é necessária para o seed de volume"
    engine = create_engine_from_url(url)
    async with engine.begin() as conn:
        if "--drop" in sys.argv:
            await remover(conn)
        else:
            await remover(conn)
            resultado = await semear(conn)
            for tabela, total in resultado.items():
                print(f"{tabela}: {total:,}".replace(",", "."))
    if "--drop" in sys.argv:
        await _vacuum(engine)
        print("seed de volume removido")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

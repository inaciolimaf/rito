"""Spec 040, alvo 3 — performance da caixa de entrada com 10.000 tarefas semeadas.

Seed em escopo de MÓDULO (uma vez por worker do xdist, em tenant próprio): 10 mil
posts pendentes + 10 mil concluídos do mesmo usuário — volume que faria N+1, scan sem
índice ou contador por seção explodirem. As medições usam o repositório direto, sob a
role da aplicação com RLS ativo (como em produção).

Os limiares são 5× o medido local (ver docs/DECISOES.md, entrada da spec 040) para o
teste não flakkar sob `pytest -n auto` com outros workers martelando o mesmo Postgres
— o número oficial da DoD é o da medição isolada documentada, não o limiar do assert.
"""

import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.inbox.repository import InboxRepository
from app.domain.inbox.sections import DEFAULT_SECTION_ORDER, InboxSection

_PENDING = 10_000
_COMPLETED = 10_000
# 5× o medido na execução isolada (≈15 ms counts, ≈5 ms página) — margem para a
# contenção do -n auto, não um alvo de performance.
_COUNTS_BUDGET_MS = 200
_PAGE_BUDGET_MS = 200


@dataclass
class PerfSeed:
    tenant_id: uuid.UUID
    user_id: uuid.UUID


@pytest.fixture(scope="module")
async def perf_seed() -> AsyncGenerator[PerfSeed]:
    """Seed próprio por worker — engine de admin criada aqui porque `admin_engine`
    (conftest) é function-scoped e este seed é module-scoped de propósito (spec 040:
    a fixture de 10 mil tarefas existe só neste arquivo, em escopo de sessão)."""
    from app.core.config import get_settings
    from app.core.db import create_engine_from_url

    url = get_settings().migrations_database_url
    assert url is not None
    admin_engine = create_engine_from_url(url)
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    async with admin_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:t, :s, 'Tenant perf')"),
            {"t": tenant_id, "s": f"perf-{tenant_id}"},
        )
        await conn.execute(
            text(
                "INSERT INTO users (id, tenant_id, email, name, role, is_active) "
                "VALUES (:u, :t, :e, 'Usuário Perf', 'GESTOR', true)"
            ),
            {"u": user_id, "t": tenant_id, "e": f"{user_id}@perf.local"},
        )
        group_id, lawsuit_type_id = uuid.uuid4(), uuid.uuid4()
        stage_id = await conn.scalar(text("SELECT id FROM stages LIMIT 1"))
        task_type_id = uuid.uuid4()
        await conn.execute(
            text("INSERT INTO action_groups (id, tenant_id, name) VALUES (:g, :t, 'Perf')"),
            {"g": group_id, "t": tenant_id},
        )
        await conn.execute(
            text(
                "INSERT INTO lawsuit_types (id, tenant_id, action_group_id, name) "
                "VALUES (:i, :t, :g, 'Perf')"
            ),
            {"i": lawsuit_type_id, "t": tenant_id, "g": group_id},
        )
        origin_id = uuid.uuid4()
        await conn.execute(
            text("INSERT INTO customer_origins (id, tenant_id, name) VALUES (:o, :t, 'Perf')"),
            {"o": origin_id, "t": tenant_id},
        )
        customer_id = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO customers (id, tenant_id, type, name, origin_id, country) "
                "VALUES (:c, :t, 'PF', 'Cliente Perf', :o, 'Brasil')"
            ),
            {"c": customer_id, "t": tenant_id, "o": origin_id},
        )
        lawsuit_id = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO lawsuits (id, tenant_id, user_id, lawsuit_type_id, stage_id) "
                "VALUES (:l, :t, :u, :lt, :st)"
            ),
            {"l": lawsuit_id, "t": tenant_id, "u": user_id, "lt": lawsuit_type_id, "st": stage_id},
        )
        await conn.execute(
            text("INSERT INTO task_types (id, tenant_id, name, reward) VALUES (:i, :t, 'Perf', 5)"),
            {"i": task_type_id, "t": tenant_id},
        )
        # 10k pendentes + 10k concluídas — as concluídas saem da caixa (regra 5) e
        # deixam o índice parcial ix_post_users_pending seletivo de verdade.
        await conn.execute(
            text(
                "INSERT INTO posts (id, tenant_id, lawsuit_id, task_type_id, created_by,"
                " scheduled_date, reward_snapshot) "
                "SELECT uuid_generate_v4(), :t, :l, :tt, :u, CURRENT_DATE, 5 "
                "FROM generate_series(1, :n)"
            ),
            {"t": tenant_id, "l": lawsuit_id, "tt": task_type_id, "u": user_id, "n": _PENDING},
        )
        await conn.execute(
            text(
                "INSERT INTO post_users (id, tenant_id, post_id, user_id) "
                "SELECT uuid_generate_v4(), :t, id, :u FROM posts WHERE tenant_id = :t"
            ),
            {"t": tenant_id, "u": user_id},
        )
        await conn.execute(
            text(
                "INSERT INTO posts (id, tenant_id, lawsuit_id, task_type_id, created_by,"
                " scheduled_date, reward_snapshot) "
                "SELECT uuid_generate_v4(), :t, :l, :tt, :u, CURRENT_DATE, 5 "
                "FROM generate_series(1, :n)"
            ),
            {"t": tenant_id, "l": lawsuit_id, "tt": task_type_id, "u": user_id, "n": _COMPLETED},
        )
        await conn.execute(
            text(
                "INSERT INTO post_users (id, tenant_id, post_id, user_id, completed_at,"
                " points_earned) "
                "SELECT uuid_generate_v4(), :t, id, :u, now(), 5 FROM posts"
                " WHERE tenant_id = :t AND id NOT IN (SELECT post_id FROM post_users"
                "   WHERE tenant_id = :t AND user_id = :u AND completed_at IS NULL)"
            ),
            {"t": tenant_id, "u": user_id},
        )
        await conn.execute(text("ANALYZE posts"))
        await conn.execute(text("ANALYZE post_users"))
    yield PerfSeed(tenant_id=tenant_id, user_id=user_id)
    async with admin_engine.begin() as conn:
        # users.tenant_id não tem CASCADE — limpa na ordem dos filhos.
        await conn.execute(text("DELETE FROM post_users WHERE tenant_id = :t"), {"t": tenant_id})
        await conn.execute(text("DELETE FROM posts WHERE tenant_id = :t"), {"t": tenant_id})
        await conn.execute(text("DELETE FROM lawsuits WHERE tenant_id = :t"), {"t": tenant_id})
        await conn.execute(text("DELETE FROM task_types WHERE tenant_id = :t"), {"t": tenant_id})
        await conn.execute(text("DELETE FROM customers WHERE tenant_id = :t"), {"t": tenant_id})
        await conn.execute(text("DELETE FROM lawsuit_types WHERE tenant_id = :t"), {"t": tenant_id})
        await conn.execute(text("DELETE FROM action_groups WHERE tenant_id = :t"), {"t": tenant_id})
        await conn.execute(
            text("DELETE FROM customer_origins WHERE tenant_id = :t"), {"t": tenant_id}
        )
        await conn.execute(text("DELETE FROM users WHERE tenant_id = :t"), {"t": tenant_id})
        await conn.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": tenant_id})
    await admin_engine.dispose()


async def test_counts_das_6_secoes_em_uma_query_rapida(
    perf_seed: PerfSeed, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, perf_seed.tenant_id)
        repo = InboxRepository(session)
        started = time.perf_counter()
        counts = await repo.counts(
            perf_seed.user_id, section_order=DEFAULT_SECTION_ORDER, today=date.today()
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

    assert elapsed_ms < _COUNTS_BUDGET_MS, f"counts levou {elapsed_ms:.0f} ms"
    # As 10k pendentes caem em "unread" (sem prazo, tipo comum, não lidas); as 10k
    # concluídas não aparecem (regra 5).
    assert counts[InboxSection.UNREAD.value] == _PENDING
    assert sum(counts.values()) == _PENDING


async def test_pagina_de_secao_rapida_e_indice_parcial_em_uso(
    perf_seed: PerfSeed, app_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, perf_seed.tenant_id)
        repo = InboxRepository(session)
        started = time.perf_counter()
        page = await repo.list_section(
            perf_seed.user_id,
            section_order=DEFAULT_SECTION_ORDER,
            section=InboxSection.UNREAD.value,
            today=date.today(),
            cursor=None,
            limit=20,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        # EXPLAIN do escopo da caixa sob RLS: acesso a post_users tem que ser indexado
        # (nunca Seq Scan). O planner escolhe o índice — com o join pequeno de
        # task_types ele prefere sair pelos posts e conferir a linha na
        # uq_post_users_post_user, que é o plano ótimo aqui.
        plan = await session.execute(
            text(
                "EXPLAIN SELECT posts.* FROM posts "
                "JOIN post_users ON post_users.post_id = posts.id"
                " AND post_users.user_id = :u "
                "JOIN task_types ON task_types.id = posts.task_type_id "
                "WHERE post_users.completed_at IS NULL AND (posts.is_future = false OR "
                "(posts.scheduled_date IS NOT NULL AND posts.scheduled_date <= CURRENT_DATE))"
            ),
            {"u": perf_seed.user_id},
        )
        plan_text = "\n".join(str(row[0]) for row in plan)

        # O índice PARCIAL de pendentes (spec 033) é a escolha quando a consulta sai
        # do lado do usuário sem o join — "minhas pendentes" pura.
        partial_plan = await session.execute(
            text(
                "EXPLAIN SELECT post_id FROM post_users "
                "WHERE user_id = :u AND completed_at IS NULL"
            ),
            {"u": perf_seed.user_id},
        )
        partial_text = "\n".join(str(row[0]) for row in partial_plan)

    assert elapsed_ms < _PAGE_BUDGET_MS, f"list_section levou {elapsed_ms:.0f} ms"
    assert len(page) == 21  # limit + 1 (keyset)
    assert "Seq Scan on post_users" not in plan_text, plan_text
    assert "ix_post_users_pending" in partial_text, partial_text

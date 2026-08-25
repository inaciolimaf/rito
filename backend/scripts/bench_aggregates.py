"""Mede o refresh de cada view materializada com volume real (spec 080, alvo 2).

Não é teste: semeia um tenant descartável com 100.000 processos, 500.000 tarefas e
200.000 lançamentos, mede `REFRESH MATERIALIZED VIEW` das oito views do registry e
apaga tudo no fim. O resultado vai para `docs/DECISOES.md` — a suíte não paga esse
custo (CLAUDE.md §3: fixture de volume só em benchmark, nunca no `make test`).

    cd backend && MIGRATIONS_DATABASE_URL=... uv run python -m scripts.bench_aggregates

Opções: `--lawsuits`, `--posts`, `--transactions`, `--keep` (não apaga o tenant).
"""

import argparse
import asyncio
import time
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.core.config import get_settings

# Ordem de refresh do worker (spec 078, regra 10: sequencial, nunca em paralelo).
VIEWS = [
    "user_monthly_scores",
    "account_daily_balances",
    "agility_daily",
    "timesheet_daily",
    "bi_pipeline_monthly",
    "bi_vintage",
    "bi_lawsuit_cycles",
    "bi_cost_allocation",
]


@dataclass
class Measurement:
    view: str
    concurrently: bool
    seconds: float
    rows: int


async def _seed(
    conn: AsyncConnection, tenant: uuid.UUID, *, lawsuits: int, posts: int, transactions: int
) -> None:
    """Semeia o mínimo de taxonomia + o volume. Datas espalhadas em 36 meses para que
    o GROUP BY mensal das views tenha cardinalidade parecida com a real."""
    await conn.execute(
        text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, 'Bench')"),
        {"id": tenant, "slug": f"bench-{tenant}"},
    )
    # `accounts` (spec 011) tem os dados cadastrais do escritório como NOT NULL — o
    # timesheet_daily junta com ele pelo timezone, então a linha precisa existir.
    await conn.execute(
        text(
            "INSERT INTO accounts (tenant_id, name, alternate_name, identification, state, "
            "city, postal_code, street, region, cellphone, phone, email, email_admin) "
            "VALUES (:t, 'Bench', 'Bench', '00000000000191', 'SP', 'São Paulo', "
            "'01001000', 'Rua Bench, 1', 'Centro', '11999999999', '1133333333', "
            ":email, :email)"
        ),
        {"t": tenant, "email": f"bench-{tenant}@example.com"},
    )
    user_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO users (id, tenant_id, email, name, password_hash, role) "
            "VALUES (:id, :t, :email, 'Bench', 'x', 'GESTOR')"
        ),
        {"id": user_id, "t": tenant, "email": f"bench-{tenant}@example.com"},
    )
    group_id = uuid.uuid4()
    await conn.execute(
        text("INSERT INTO action_groups (id, tenant_id, name) VALUES (:id, :t, 'Bench')"),
        {"id": group_id, "t": tenant},
    )
    type_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO lawsuit_types (id, tenant_id, action_group_id, name) "
            "VALUES (:id, :t, :g, 'Bench')"
        ),
        {"id": type_id, "t": tenant, "g": group_id},
    )
    stage_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO stages (id, tenant_id, step_id, name, position) "
            "VALUES (:id, :t, 3, 'Bench', 1)"
        ),
        {"id": stage_id, "t": tenant},
    )
    task_type_id = uuid.uuid4()
    await conn.execute(
        text("INSERT INTO task_types (id, tenant_id, name, reward) VALUES (:id, :t, 'Bench', 5)"),
        {"id": task_type_id, "t": tenant},
    )
    category_id = uuid.uuid4()
    await conn.execute(
        text(
            "INSERT INTO financial_categories (id, tenant_id, name, type, dre_group_id) "
            "VALUES (:id, :t, 'Bench', 'DESPESA', 6)"
        ),
        {"id": category_id, "t": tenant},
    )
    # ck_tx_non_transfer_needs_category: despesa exige categoria E centro de custo.
    cost_center_id = uuid.uuid4()
    await conn.execute(
        text("INSERT INTO cost_centers (id, tenant_id, name) VALUES (:id, :t, 'Bench')"),
        {"id": cost_center_id, "t": tenant},
    )

    await conn.execute(
        text("""
            INSERT INTO lawsuits (
                tenant_id, user_id, lawsuit_type_id, stage_id, created_at, case_value,
                fees_value, closure_date, transit_date, archived_date, outcome
            )
            SELECT :t, :u, :lt, :st,
                   now() - ((n % 1080) || ' days')::interval,
                   1000 + (n % 500) * 10,
                   100 + (n % 50) * 10,
                   -- ck_cycle: fechamento <= trânsito <= arquivamento (spec 022, regra 3).
                   CASE WHEN n % 3 = 0
                        THEN (now() - ((n % 900) || ' days')::interval)::date END,
                   CASE WHEN n % 3 = 0
                        THEN (now() - ((n % 900 - 30) || ' days')::interval)::date END,
                   CASE WHEN n % 6 = 0
                        THEN (now() - ((n % 900 - 60) || ' days')::interval)::date END,
                   CASE WHEN n % 3 = 0 THEN 'GANHO'::lawsuit_outcome END
            FROM generate_series(1, :count) AS n
            """),
        {"t": tenant, "u": user_id, "lt": type_id, "st": stage_id, "count": lawsuits},
    )

    await conn.execute(
        text("""
            INSERT INTO posts (tenant_id, lawsuit_id, task_type_id, created_by,
                               scheduled_date, deadline_date, reward_snapshot, created_at)
            SELECT :t, l.id, :tt, :u,
                   (now() - ((n % 400) || ' days')::interval)::date,
                   (now() - ((n % 400) || ' days')::interval)::date,
                   5,
                   now() - ((n % 400) || ' days')::interval
            FROM generate_series(1, :count) AS n
            -- row_number em vez de OFFSET por processo: com 500 mil tarefas, um OFFSET
            -- por linha viraria varredura quadrática.
            JOIN (
                SELECT id, row_number() OVER (ORDER BY id) AS rn
                  FROM lawsuits WHERE tenant_id = :t
            ) l ON l.rn = ((n - 1) % :lawsuits) + 1
            """),
        {"t": tenant, "tt": task_type_id, "u": user_id, "count": posts, "lawsuits": lawsuits},
    )
    await conn.execute(
        text("""
            INSERT INTO post_users (tenant_id, post_id, user_id, completed_at, points_earned)
            SELECT :t, p.id, :u,
                   CASE WHEN random() < 0.7 THEN p.created_at + interval '2 days' END,
                   CASE WHEN random() < 0.7 THEN 5 END
            FROM posts p WHERE p.tenant_id = :t
            """),
        {"t": tenant, "u": user_id},
    )

    await conn.execute(
        text("""
            INSERT INTO transactions (tenant_id, kind, user_id, category_id, cost_center_id,
                                      amount, due_date, competence, payment_date, created_at)
            SELECT :t, 'DESPESA'::transaction_kind, :u, :c, :cc,
                   50 + (n % 200),
                   (now() - ((n % 1000) || ' days')::interval)::date,
                   date_trunc('month', now() - ((n % 1000) || ' days')::interval)::date,
                   CASE WHEN n % 4 <> 0
                        THEN (now() - ((n % 1000) || ' days')::interval)::date END,
                   now() - ((n % 1000) || ' days')::interval
            FROM generate_series(1, :count) AS n
            """),
        {
            "t": tenant,
            "u": user_id,
            "c": category_id,
            "cc": cost_center_id,
            "count": transactions,
        },
    )


async def _refresh(conn: AsyncConnection, view: str) -> Measurement:
    """CONCURRENTLY quando há índice único (todas as oito têm) — é o que o worker usa,
    e é o que garante leitura sem bloqueio durante o refresh."""
    has_unique = await conn.scalar(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid = i.indrelid "
            "WHERE c.relname = :view AND i.indisunique)"
        ),
        {"view": view},
    )
    started = time.monotonic()
    await conn.execute(
        text(f"REFRESH MATERIALIZED VIEW {'CONCURRENTLY ' if has_unique else ''}{view}")
    )
    elapsed = time.monotonic() - started
    rows = await conn.scalar(text(f"SELECT count(*) FROM {view}"))
    return Measurement(
        view=view, concurrently=bool(has_unique), seconds=elapsed, rows=int(rows or 0)
    )


async def _read_during_refresh(engine_url: str, view: str) -> tuple[float, float]:
    """Prova que CONCURRENTLY não bloqueia leitura: dispara o refresh numa conexão e
    lê a view em outra ao mesmo tempo. Devolve (segundos do refresh, segundos da leitura)."""
    refresh_engine = create_async_engine(engine_url, isolation_level="AUTOCOMMIT")
    read_engine = create_async_engine(engine_url, isolation_level="AUTOCOMMIT")

    async def refresh() -> float:
        started = time.monotonic()
        async with refresh_engine.connect() as conn:
            await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
        return time.monotonic() - started

    async def read() -> float:
        await asyncio.sleep(0.05)  # deixa o refresh começar antes da leitura
        started = time.monotonic()
        async with read_engine.connect() as conn:
            await conn.execute(text(f"SELECT count(*) FROM {view}"))
        return time.monotonic() - started

    refresh_seconds, read_seconds = await asyncio.gather(refresh(), read())
    await refresh_engine.dispose()
    await read_engine.dispose()
    return refresh_seconds, read_seconds


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lawsuits", type=int, default=100_000)
    parser.add_argument("--posts", type=int, default=500_000)
    parser.add_argument("--transactions", type=int, default=200_000)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    url = get_settings().migrations_database_url
    assert url is not None, "MIGRATIONS_DATABASE_URL é obrigatória (refresh roda como superusuário)"

    tenant = uuid.uuid4()
    engine = create_async_engine(url)
    print(f"tenant de bench: {tenant}")

    started = time.monotonic()
    async with engine.begin() as conn:
        await _seed(
            conn,
            tenant,
            lawsuits=args.lawsuits,
            posts=args.posts,
            transactions=args.transactions,
        )
    print(f"seed: {time.monotonic() - started:.1f}s")

    autocommit = create_async_engine(url, isolation_level="AUTOCOMMIT")
    measurements: list[Measurement] = []
    async with autocommit.connect() as conn:
        for view in VIEWS:
            measurements.append(await _refresh(conn, view))
    await autocommit.dispose()

    print(f"\n{'view':<26}{'modo':<14}{'segundos':>10}{'linhas':>12}")
    for m in measurements:
        modo = "CONCURRENTLY" if m.concurrently else "completo"
        print(f"{m.view:<26}{modo:<14}{m.seconds:>10.2f}{m.rows:>12}")

    lento = max(measurements, key=lambda m: m.seconds)
    refresh_seconds, read_seconds = await _read_during_refresh(url, lento.view)
    print(
        f"\nleitura concorrente em {lento.view}: refresh {refresh_seconds:.2f}s, "
        f"SELECT {read_seconds:.2f}s (não bloqueou)"
    )

    if not args.keep:
        # Na ordem das FKs — `TRUNCATE ... CASCADE` (o que o runner de teste usa) levaria
        # junto o banco inteiro, não só o tenant do bench.
        async with engine.begin() as conn:
            for table in (
                "post_users",
                "posts",
                "transactions",
                "lawsuits",
                "stages",
                "task_types",
                "lawsuit_types",
                "action_groups",
                "financial_categories",
                "cost_centers",
                "users",
                "accounts",
            ):
                await conn.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id = :id"), {"id": tenant}
                )
            await conn.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": tenant})
        # As views ficam com as linhas do bench até o próximo refresh — refresca de novo
        # para não deixar lixo materializado para a suíte.
        autocommit = create_async_engine(url, isolation_level="AUTOCOMMIT")
        async with autocommit.connect() as conn:
            for view in VIEWS:
                await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
        await autocommit.dispose()
        print("tenant de bench removido e views refrescadas")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

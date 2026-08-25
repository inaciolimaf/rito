"""Padrão de agregação por view materializada (refatoração 060, Alvo 2).

`user_monthly_scores` (spec 039) e `account_daily_balances` (spec 059) repetiam a
mesma mecânica ponto a ponto — REFRESH CONCURRENTLY como superusuário, em AUTOCOMMIT,
porque a role de aplicação está sob FORCE RLS e REFRESH CONCURRENTLY não roda dentro
de transação. `074`–`077` (BI) vão criar mais quatro views no mesmo molde; esta é a
peça compartilhada — cada worker de domínio (`app/workers/scores.py`,
`app/workers/financial_dashboard.py`) fica só com o `MaterializedViewSpec` e o
wrapper fino que os testes já chamam pelo nome (`refresh_user_monthly_scores`,
`refresh_account_daily_balances`), sem duplicar a conexão AUTOCOMMIT.
"""

from dataclasses import dataclass

from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import create_engine_from_url


@dataclass(frozen=True)
class MaterializedViewSpec:
    """Registro central (Alvo 2): nome da view, intervalo de refresh do beat (a
    "métrica de defasagem" que a UI mostra é derivada deste intervalo — ver
    `staleness_hint`) e uma descrição curta de quem consome."""

    view_name: str
    refresh_interval_minutes: int
    description: str

    def staleness_hint(self) -> str:
        """Texto pronto pra UI avisar a defasagem máxima (regra "métrica de
        defasagem exposta na UI") sem precisar rastrear o timestamp real do
        último refresh — o pior caso é sempre o intervalo do beat."""
        return (
            f"Pode levar até {self.refresh_interval_minutes} min para refletir mudanças recentes."
        )


MATERIALIZED_VIEWS: list[MaterializedViewSpec] = [
    MaterializedViewSpec(
        view_name="user_monthly_scores",
        refresh_interval_minutes=15,
        description="Taskscore (spec 039) — pontuação mensal por usuário.",
    ),
    MaterializedViewSpec(
        view_name="account_daily_balances",
        refresh_interval_minutes=10,
        description="Financeiro (spec 059) — saldo diário cumulativo por conta.",
    ),
    MaterializedViewSpec(
        view_name="agility_daily",
        refresh_interval_minutes=15,
        description="Relatórios (spec 071) — agilidade diária por usuário.",
    ),
    MaterializedViewSpec(
        view_name="timesheet_daily",
        refresh_interval_minutes=15,
        description="Livro de ponto (spec 073) — primeiro/último acesso por dia.",
    ),
    MaterializedViewSpec(
        view_name="bi_pipeline_monthly",
        refresh_interval_minutes=480,
        description="BI (spec 074) — funil mensal por grupo de ação (coorte de criação).",
    ),
    MaterializedViewSpec(
        view_name="bi_vintage",
        refresh_interval_minutes=480,
        description="BI (spec 075) — safra anual por grupo de ação (ano de closure_date).",
    ),
    MaterializedViewSpec(
        view_name="bi_lawsuit_cycles",
        refresh_interval_minutes=480,
        description="BI (spec 076) — ciclos e receita por processo fechado.",
    ),
    MaterializedViewSpec(
        view_name="bi_cost_allocation",
        refresh_interval_minutes=480,
        description="BI (spec 077) — custo fixo, marketing e custo por ponto por competência.",
    ),
]


async def refresh_materialized_view_concurrently(view_name: str, url: str | None = None) -> None:
    """REFRESH CONCURRENTLY como superusuário, em AUTOCOMMIT.

    Duas particularidades de matview num setup com RLS, válidas para qualquer view
    registrada em `MATERIALIZED_VIEWS`:

    - REFRESH exige ser dono da view E enxergar todas as linhas; a role de aplicação
      (rito_app) está sob FORCE RLS e sem `app.tenant_id` veria zero linhas — o
      refresh esvaziaria a view. Por isso roda com a MIGRATIONS_DATABASE_URL
      (superusuário), como a fixture `admin_engine` dos testes.
    - REFRESH ... CONCURRENTLY não roda dentro de transação, então a conexão vai em
      AUTOCOMMIT.

    Recebe a URL para os testes chamarem direto com a MIGRATIONS_DATABASE_URL de
    teste, sem passar pela fila.
    """
    # SQL de REFRESH não aceita identificador de view como bind param — o nome só
    # pode vir de MATERIALIZED_VIEWS (nunca de entrada externa), igual ao mesmo
    # padrão já usado nas migrations (f-string com identificador fixo do código).
    known_views = {spec.view_name for spec in MATERIALIZED_VIEWS}
    if view_name not in known_views:
        raise ValueError(f"View não registrada em MATERIALIZED_VIEWS: {view_name!r}")
    resolved = url or get_settings().migrations_database_url
    if resolved is None:
        raise RuntimeError("MIGRATIONS_DATABASE_URL não configurada para o refresh.")
    engine = create_engine_from_url(resolved)
    try:
        conn = await engine.connect()
        try:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            await conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"))
        finally:
            await conn.close()
    finally:
        await engine.dispose()

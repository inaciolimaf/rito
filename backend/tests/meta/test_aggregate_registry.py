"""Testes meta da spec 078 (regras 1 e 3):

- toda view materializada do banco está no aggregate_registry (e todo registro aponta
  para uma view real — registro órfão quebraria o refresh do orquestrador);
- toda view materializada tem índice único, exigência do REFRESH ... CONCURRENTLY.

Rodam contra o rito_test já migrado (spec 009, regra 3) com a engine de superusuário.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def test_toda_view_materializada_esta_no_registry(admin_engine: AsyncEngine) -> None:
    async with admin_engine.connect() as conn:
        matviews = {
            row[0]
            for row in (
                await conn.execute(
                    text("SELECT matviewname FROM pg_matviews WHERE schemaname = 'public'")
                )
            ).all()
        }
        registered = {
            row[0]
            for row in (await conn.execute(text("SELECT name FROM aggregate_registry"))).all()
        }

    assert (
        matviews - registered == set()
    ), f"Views materializadas fora do aggregate_registry: {sorted(matviews - registered)}"
    assert registered - matviews == set(), (
        f"Registros órfãos no aggregate_registry (view não existe): "
        f"{sorted(registered - matviews)}"
    )


async def test_toda_view_materializada_tem_indice_unico(admin_engine: AsyncEngine) -> None:
    """REFRESH MATERIALIZED VIEW CONCURRENTLY (regra 3) exige pelo menos um índice
    único — sem ele o refresh do orquestrador falha em runtime."""
    async with admin_engine.connect() as conn:
        without_unique = {
            row[0]
            for row in (
                await conn.execute(
                    text(
                        "SELECT c.relname FROM pg_class c "
                        "WHERE c.relkind = 'm' AND c.relnamespace = 'public'::regnamespace "
                        "AND NOT EXISTS ("
                        "  SELECT 1 FROM pg_index i WHERE i.indrelid = c.oid AND i.indisunique"
                        ")"
                    )
                )
            ).all()
        }

    assert without_unique == set(), (
        f"Views materializadas sem índice único (CONCURRENTLY impossível): "
        f"{sorted(without_unique)}"
    )

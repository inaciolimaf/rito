import uuid

from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg

from app.core.models import Tenant
from app.core.repository import build_keyset_query

# O construtor do dialect não tem stub de tipos completo no SQLAlchemy — só usado
# aqui para compilar SQL literal em teste, não em código de produção.
_PG_DIALECT = PGDialect_asyncpg()  # type: ignore[no-untyped-call]


def test_build_keyset_query_without_cursor_orders_and_limits() -> None:
    stmt = build_keyset_query(Tenant, cursor=None, limit=10)
    compiled = str(stmt.compile(dialect=_PG_DIALECT, compile_kwargs={"literal_binds": True}))

    assert "ORDER BY tenants.id" in compiled
    assert "LIMIT 10" in compiled
    assert "WHERE" not in compiled


def test_build_keyset_query_with_cursor_filters_by_id() -> None:
    cursor = uuid.uuid4()
    stmt = build_keyset_query(Tenant, cursor=cursor, limit=5)
    compiled = str(stmt.compile(dialect=_PG_DIALECT, compile_kwargs={"literal_binds": True}))

    assert f"tenants.id > '{cursor}'" in compiled
    assert "LIMIT 5" in compiled

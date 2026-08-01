import uuid

from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg

from app.core.repository import build_sorted_keyset_query, decode_cursor, encode_cursor
from app.domain.users.models import User

# O construtor do dialect não tem stub de tipos completo no SQLAlchemy — só usado
# aqui para compilar SQL literal em teste, não em código de produção.
_PG_DIALECT = PGDialect_asyncpg()  # type: ignore[no-untyped-call]


def test_encode_decode_cursor_roundtrip() -> None:
    id_ = uuid.uuid4()
    cursor = encode_cursor("Ana", id_)

    sort_value, decoded_id = decode_cursor(cursor)

    assert sort_value == "Ana"
    assert decoded_id == id_


def test_build_sorted_keyset_query_without_cursor_orders_by_column_then_id() -> None:
    stmt = build_sorted_keyset_query(User, sort_column=User.name, cursor=None, limit=10)
    compiled = str(stmt.compile(dialect=_PG_DIALECT, compile_kwargs={"literal_binds": True}))

    assert "ORDER BY users.name, users.id" in compiled
    assert "LIMIT 10" in compiled
    assert "WHERE" not in compiled


def test_build_sorted_keyset_query_with_cursor_filters_by_tuple() -> None:
    cursor_id = uuid.uuid4()
    stmt = build_sorted_keyset_query(
        User, sort_column=User.name, cursor=("Ana", cursor_id), limit=5
    )
    compiled = str(stmt.compile(dialect=_PG_DIALECT, compile_kwargs={"literal_binds": True}))

    assert "(users.name, users.id) > ('Ana'" in compiled
    assert str(cursor_id) in compiled
    assert "LIMIT 5" in compiled

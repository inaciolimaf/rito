import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()

SessionFactory = async_sessionmaker[AsyncSession]

# current_setting('app.tenant_id', true) só devolve NULL numa conexão que nunca
# tocou o GUC; numa conexão já usada por outro tenant (pool reciclado), o
# Postgres cria um placeholder cujo valor "resetado" é '' — o cast ::uuid desse
# valor levanta erro em vez de devolver NULL. Ambos os casos são seguros (nunca
# vazam linhas); só o formato do "não vazamento" muda.
_UNSET_TENANT_ERRORS = (DBAPIError,)


async def _insert_row(
    session_factory: SessionFactory, table: str, tenant_id: uuid.UUID, label: str
) -> uuid.UUID:
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        result = await session.execute(
            text(
                f"INSERT INTO {table} (tenant_id, label) "
                "VALUES (:tenant_id, :label) RETURNING id"
            ),
            {"tenant_id": str(tenant_id), "label": label},
        )
        return result.scalar_one()  # type: ignore[no-any-return]


async def test_tenant_a_does_not_see_tenant_b_row(
    app_session_factory: SessionFactory, tenant_probe_table: str
) -> None:
    await _insert_row(app_session_factory, tenant_probe_table, TENANT_A, "linha-a")
    await _insert_row(app_session_factory, tenant_probe_table, TENANT_B, "linha-b")

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, TENANT_A)
        result = await session.execute(text(f"SELECT label FROM {tenant_probe_table}"))
        labels = [row[0] for row in result.all()]

    assert labels == ["linha-a"]


async def test_insert_with_foreign_tenant_id_is_rejected(
    app_session_factory: SessionFactory, tenant_probe_table: str
) -> None:
    async with app_session_factory() as session:
        with pytest.raises(DBAPIError):
            async with session.begin():
                await set_tenant_context(session, TENANT_A)
                await session.execute(
                    text(
                        f"INSERT INTO {tenant_probe_table} (tenant_id, label) "
                        "VALUES (:tenant_id, :label)"
                    ),
                    {"tenant_id": str(TENANT_B), "label": "cross-tenant"},
                )


async def test_update_and_delete_do_not_cross_tenant(
    app_session_factory: SessionFactory, tenant_probe_table: str
) -> None:
    row_id = await _insert_row(
        app_session_factory, tenant_probe_table, TENANT_B, "linha-b-protegida"
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, TENANT_A)

        update_result = await session.execute(
            text(f"UPDATE {tenant_probe_table} SET label = 'hackeado' WHERE id = :id"),
            {"id": str(row_id)},
        )
        assert isinstance(update_result, CursorResult)
        assert update_result.rowcount == 0

        delete_result = await session.execute(
            text(f"DELETE FROM {tenant_probe_table} WHERE id = :id"), {"id": str(row_id)}
        )
        assert isinstance(delete_result, CursorResult)
        assert delete_result.rowcount == 0

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, TENANT_B)
        result = await session.execute(
            text(f"SELECT label FROM {tenant_probe_table} WHERE id = :id"), {"id": str(row_id)}
        )
        assert result.scalar_one() == "linha-b-protegida"


async def test_query_without_tenant_context_returns_zero_rows(
    app_session_factory: SessionFactory, tenant_probe_table: str
) -> None:
    await _insert_row(app_session_factory, tenant_probe_table, TENANT_A, "linha-sem-contexto")

    async with app_session_factory() as session, session.begin():
        try:
            result = await session.execute(text(f"SELECT * FROM {tenant_probe_table}"))
            rows = result.all()
        except _UNSET_TENANT_ERRORS:
            rows = []

        assert rows == []


async def test_tenant_context_does_not_leak_between_transactions(
    app_session_factory: SessionFactory, tenant_probe_table: str
) -> None:
    async with app_session_factory() as session:
        async with session.begin():
            await set_tenant_context(session, TENANT_A)
            result = await session.execute(text("SELECT current_setting('app.tenant_id', true)"))
            assert result.scalar() == str(TENANT_A)

        async with session.begin():
            result = await session.execute(text("SELECT current_setting('app.tenant_id', true)"))
            assert result.scalar() in (None, "")

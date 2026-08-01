"""BaseRepository (CLAUDE.md §6) contra Postgres de verdade — todo repositório de
domínio futuro herda daqui, então um bug aqui quebraria todos eles silenciosamente.
list_paginated/delete não tinham nenhum teste de integração (spec 010, checklist)."""

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.users.repository import UserRepository
from tests.integration.conftest import SeededUser


async def test_list_paginated_ordena_por_id_e_pagina_por_cursor(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await make_user()
    tenant_id = first.tenant_id
    second = await make_user(tenant_id=tenant_id)
    third = await make_user(tenant_id=tenant_id)
    expected_ids = sorted([first.user_id, second.user_id, third.user_id])

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        repo = UserRepository(session)

        first_page = await repo.list_paginated(limit=2)
        assert [u.id for u in first_page] == expected_ids[:2]

        second_page = await repo.list_paginated(limit=2, cursor=first_page[-1].id)
        assert [u.id for u in second_page] == expected_ids[2:]


async def test_delete_remove_a_linha(
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    seeded = await make_user()

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        repo = UserRepository(session)
        user = await repo.get_by_id(seeded.user_id)
        assert user is not None
        await repo.delete(user)

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, seeded.tenant_id)
        assert await UserRepository(session).get_by_id(seeded.user_id) is None

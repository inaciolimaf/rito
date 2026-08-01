"""Semeia o tenant + usuário fixos usados pela jornada e2e (spec 006).

Idempotente: pode rodar toda vez antes do Playwright sem duplicar nada.
"""

import asyncio
import uuid

from app.core.db import create_engine, create_session_factory
from app.core.models import Tenant
from app.core.rls import set_tenant_context
from app.core.security import hash_password
from app.domain.users.models import User

E2E_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e2")
E2E_USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000e3")
E2E_EMAIL = "e2e@rito.app"
E2E_PASSWORD = "SenhaE2E123!"


async def main() -> None:
    engine = create_engine()
    session_factory = create_session_factory(engine)

    async with session_factory() as session, session.begin():
        existing_tenant = await session.get(Tenant, E2E_TENANT_ID)
        if existing_tenant is None:
            session.add(Tenant(id=E2E_TENANT_ID, slug="e2e", name="Tenant E2E"))

    async with session_factory() as session, session.begin():
        await set_tenant_context(session, E2E_TENANT_ID)
        existing_user = await session.get(User, E2E_USER_ID)
        if existing_user is None:
            session.add(
                User(
                    id=E2E_USER_ID,
                    tenant_id=E2E_TENANT_ID,
                    email=E2E_EMAIL,
                    password_hash=hash_password(E2E_PASSWORD),
                    name="Usuário E2E",
                )
            )
        else:
            existing_user.password_hash = hash_password(E2E_PASSWORD)
            existing_user.is_active = True

    await engine.dispose()
    print(f"Seed e2e ok: tenant={E2E_TENANT_ID} user={E2E_USER_ID}")


if __name__ == "__main__":
    asyncio.run(main())

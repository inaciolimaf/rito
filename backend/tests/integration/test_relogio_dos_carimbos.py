"""Duas linhas criadas na mesma transação têm `created_at` diferentes (dívida 31).

A spec 105 passou a rodar cada teste dentro de UMA transação. Com `server_default=now()` —
que no Postgres é o instante de início da transação, não o do statement — todas as linhas
criadas num mesmo teste nasciam com o mesmo `created_at`, por mais requisições HTTP separadas
que as tivessem criado.

Empatado o valor de ordenação, `paginate_keyset` desempatava por `id`, que é UUID v4: o
veredito de qualquer teste de ordenação por data passava a depender de qual UUID aleatório
saiu maior. `test_ordenacao_por_created_at_desc_por_padrao` falhava em ~metade das execuções
no HEAD limpo — e um PR que quebrasse a ordenação de verdade tinha a mesma metade de chance
de passar.

Este teste é o gate que faltava: ele afirma o MECANISMO, não uma manifestação. A spec 106
corrigiu o teste de contatos fazendo-o escrever os próprios timestamps, mas isso não impedia
o próximo teste de cair na mesma armadilha — só ainda não tinha dado azar.
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.customer_origins.models import CustomerOrigin
from app.domain.customers.models import Customer, PersonType
from tests.integration.conftest import SeededUser

pytestmark = pytest.mark.asyncio


async def test_linhas_da_mesma_transacao_nao_empatam_no_created_at(
    app_session_factory: async_sessionmaker[AsyncSession],
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """O carimbo é do STATEMENT, não da transação — é o que a migration 124 troca."""
    user = await make_user()
    async with app_session_factory() as app_session, app_session.begin():
        await set_tenant_context(app_session, user.tenant_id)
        origem = CustomerOrigin(tenant_id=user.tenant_id, name=f"Origem {uuid.uuid4().hex[:6]}")
        app_session.add(origem)
        await app_session.flush()

        # Dois `INSERT` em comandos separados, na MESMA transação — exatamente o que duas
        # requisições HTTP fazem dentro de um teste desde a spec 105.
        for nome in ("Primeiro", "Segundo"):
            app_session.add(
                Customer(
                    tenant_id=user.tenant_id,
                    type=PersonType.PF,
                    name=nome,
                    origin_id=origem.id,
                )
            )
            await app_session.flush()

        carimbos = (
            await app_session.scalars(
                select(Customer.created_at)
                .where(Customer.tenant_id == user.tenant_id)
                .order_by(Customer.created_at)
            )
        ).all()

        assert len(carimbos) == 2
        assert carimbos[0] != carimbos[1], (
            "os dois contatos nasceram com o MESMO `created_at` — o default voltou a ser `now()`, "
            "que é o instante de início da transação. Toda ordenação por data volta a ser sorteio "
            "dentro de um teste (dívida 31)."
        )

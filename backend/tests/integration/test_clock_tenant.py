"""«Hoje» é o hoje do escritório, não o do servidor (spec 114, regras 3 e 6).

## Por que este arquivo não afirma «os dois tenants veem dias diferentes»

A spec pede a prova de que dois escritórios em fusos distintos podem receber dias
diferentes. Escrever isso literalmente daria um teste que **só passa numa janela de
poucas horas por dia**: `America/Rio_Branco` (UTC−5) e `Atlantic/Azores` (UTC−1 no
verão) são as duas pontas de `ALLOWED_TIMEZONES`, e os dias dos dois divergem apenas
enquanto o relógio de Azores já virou e o de Rio Branco não.

Um teste assim é a dívida 30 outra vez — suíte que fica vermelha por causa da hora —, e
o remédio não pode ter a doença. Então a afirmação central aqui é mais forte e vale 24
horas por dia: **cada tenant recebe o dia do SEU fuso**, calculado no próprio teste com
`ZoneInfo`. Se o app lesse o relógio do processo, essa igualdade quebraria para pelo
menos um dos dois sempre que os fusos divergissem — e, quando divergem, o teste também
exige que as duas respostas sejam de fato diferentes, sem depender de sorte para isso.

A prova de que fusos distintos produzem dias distintos, essa sim determinística em todo
instante, mora em `tests/unit/test_clock.py`, que usa dois fusos a 25 horas de distância.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.permissions import FinancialAccess, UserRole
from app.core.rls import set_tenant_context
from app.domain.account.models import Account, AccountPlan
from tests.integration.conftest import SeededUser, auth_header

pytestmark = pytest.mark.asyncio

# As duas pontas de ALLOWED_TIMEZONES: 4 h de diferença no inverno, 5 h no horário de
# verão dos Açores. É a maior janela que o produto consegue produzir de verdade — e é
# de propósito que o teste não use um fuso fora dessa lista só para alargar a diferença:
# um estado que a API não deixa criar não é um estado que valha a pena afirmar.
FUSO_OESTE = "America/Rio_Branco"
FUSO_LESTE = "Atlantic/Azores"


async def _criar_conta(
    session_factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID, timezone: str
) -> None:
    """Conta do escritório com um fuso escolhido.

    `make_user` cria tenant e usuário, mas não a conta — é justamente por isso que o
    resto da suíte cai em `DEFAULT_TIMEZONE`. Aqui a conta existe e diz o fuso.
    """
    async with session_factory() as session, session.begin():
        await set_tenant_context(session, tenant_id)
        session.add(
            Account(
                tenant_id=tenant_id,
                name="Escritório de Teste",
                alternate_name="Teste",
                identification="12345678000199",
                state="AC",
                city="Rio Branco",
                postal_code="69900-000",
                street="Rua Um",
                region="Centro",
                cellphone="68999999999",
                phone="6832222222",
                email="contato@example.com",
                email_admin="admin@example.com",
                timezone=timezone,
                plan=AccountPlan.ESSENCIAL,
            )
        )


async def _criar_contato_aniversariante(
    client: AsyncClient, headers: dict[str, str], *, nome: str, dia: date
) -> str:
    """Contato cujo aniversário cai em `dia` (o ano não importa — regra 6 da spec 019)."""
    origem = await client.post(
        "/api/v1/customer-origins", json={"name": f"Origem {nome}"}, headers=headers
    )
    assert origem.status_code == 201, origem.text
    resposta = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": nome,
            "origin_id": origem.json()["id"],
            "birthdate": dia.replace(year=1990).isoformat(),
        },
        headers=headers,
    )
    assert resposta.status_code == 201, resposta.text
    return str(resposta.json()["id"])


async def test_cada_tenant_recebe_o_dia_do_proprio_fuso(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 3: o «hoje» de cada escritório sai do fuso da conta dele."""
    oeste = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    leste = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    await _criar_conta(app_session_factory, oeste.tenant_id, FUSO_OESTE)
    await _criar_conta(app_session_factory, leste.tenant_id, FUSO_LESTE)

    # O instante é único; o que muda é quem lê o relógio. Capturado ANTES das requisições
    # para que a expectativa não escorregue se a virada acontecer no meio do teste.
    agora = datetime.now(tz=ZoneInfo("UTC"))
    dia_oeste = agora.astimezone(ZoneInfo(FUSO_OESTE)).date()
    dia_leste = agora.astimezone(ZoneInfo(FUSO_LESTE)).date()

    await _criar_contato_aniversariante(
        client, auth_header(oeste), nome="Aniversariante do Oeste", dia=dia_oeste
    )
    await _criar_contato_aniversariante(
        client, auth_header(leste), nome="Aniversariante do Leste", dia=dia_leste
    )

    resposta_oeste = await client.get(
        "/api/v1/customers", params={"birthdays": "day"}, headers=auth_header(oeste)
    )
    resposta_leste = await client.get(
        "/api/v1/customers", params={"birthdays": "day"}, headers=auth_header(leste)
    )

    assert resposta_oeste.status_code == 200, resposta_oeste.text
    assert resposta_leste.status_code == 200, resposta_leste.text

    # Cada um enxerga o próprio aniversariante — a afirmação que vale a qualquer hora.
    nomes_oeste = {item["name"] for item in resposta_oeste.json()["items"]}
    nomes_leste = {item["name"] for item in resposta_leste.json()["items"]}
    assert "Aniversariante do Oeste" in nomes_oeste
    assert "Aniversariante do Leste" in nomes_leste

    # E, quando os dois fusos estão em dias diferentes, a divergência tem que aparecer:
    # é a janela em que ler o relógio do servidor daria a resposta errada para um deles.
    if dia_oeste != dia_leste:
        assert dia_leste == dia_oeste + timedelta(days=1)


async def test_relogio_nao_enxerga_a_conta_de_outro_tenant(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O fuso vem por JOIN na query de autenticação, e o RLS vale nela como em qualquer
    outra: um tenant sem conta cai em `DEFAULT_TIMEZONE`, nunca no fuso do vizinho.

    Sem esta garantia, o `outerjoin` seria um caminho novo para vazar dado entre
    escritórios — e o §4 do CLAUDE.md exige o teste de isolamento para toda tabela que
    entra numa consulta nova.
    """
    com_conta = await make_user(role=UserRole.GESTOR)
    sem_conta = await make_user(role=UserRole.GESTOR)
    await _criar_conta(app_session_factory, com_conta.tenant_id, FUSO_LESTE)

    agora = datetime.now(tz=ZoneInfo("UTC"))
    dia_padrao = agora.astimezone(ZoneInfo("America/Sao_Paulo")).date()

    await _criar_contato_aniversariante(
        client, auth_header(sem_conta), nome="Sem Conta", dia=dia_padrao
    )
    resposta = await client.get(
        "/api/v1/customers", params={"birthdays": "day"}, headers=auth_header(sem_conta)
    )

    assert resposta.status_code == 200, resposta.text
    # Caiu no padrão, não no fuso de quem tem conta.
    assert "Sem Conta" in {item["name"] for item in resposta.json()["items"]}

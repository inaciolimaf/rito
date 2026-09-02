"""API pública v1 (spec 095 §8).

O teste que carrega a spec é o de isolamento: um token é uma credencial que vive fora do
prédio, em script de terceiro, e se ele lesse dado de outro escritório o vazamento seria
silencioso e permanente. Todo o resto — escopo, limite, log — protege esse mesmo ponto.
"""

import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.clock import Clock
from app.core.rls import set_tenant_context
from app.domain.account.models import DEFAULT_TIMEZONE
from app.domain.api_tokens.models import ApiRequest, ApiToken
from app.domain.api_tokens.service import MAX_ACTIVE_TOKENS
from app.domain.users.models import UserRole
from app.public.deps import GET_LIMIT_PER_MINUTE
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_customers import _create_origin
from tests.integration.test_lawsuits import _auth_header

pytestmark = pytest.mark.asyncio

TODOS_OS_ESCOPOS = [
    "read:settings",
    "read:customers",
    "write:customers",
    "read:lawsuits",
    "write:lawsuits",
    "read:posts",
    "write:posts",
    "read:publications",
    "read:transactions",
    "write:transactions",
    "read:documents",
]


@pytest.fixture(autouse=True)
async def _limpar_limites() -> Any:
    """O limite vive no Redis e atravessa testes: sem limpar, o segundo teste do arquivo
    herdaria o contador do primeiro."""
    from redis.asyncio import Redis

    from app.core.config import get_settings

    settings = get_settings()
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    chaves = [chave async for chave in redis.scan_iter("api:rl:*")]
    if chaves:
        await redis.delete(*chaves)
    yield
    await redis.aclose()


async def _criar_token(
    client: AsyncClient,
    user: SeededUser,
    *,
    scopes: list[str] | None = None,
    allowed_ips: list[str] | None = None,
    expires_at: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    resposta = await client.post(
        "/api/v1/api-tokens",
        json={
            "name": f"Integração {uuid.uuid4().hex[:6]}",
            "scopes": scopes or TODOS_OS_ESCOPOS,
            "allowed_ips": allowed_ips or [],
            "expires_at": expires_at.isoformat() if expires_at else None,
        },
        headers=auth_header(user),
    )
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    return corpo["token"], corpo


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------- autenticação


async def test_token_valido_autentica_e_resolve_o_tenant(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    token, _corpo = await _criar_token(client, user)

    resposta = await client.get("/api/public/v1/settings", headers=_bearer(token))

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["tenant_id"] == str(user.tenant_id)
    assert any(item["id"] == str(user.user_id) for item in resposta.json()["users"])


async def test_token_ausente_invalido_expirado_e_revogado_dao_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)

    sem_token = await client.get("/api/public/v1/settings")
    assert sem_token.status_code == 401

    invalido = await client.get("/api/public/v1/settings", headers=_bearer("rito_naoexiste"))
    assert invalido.status_code == 401

    expirado, _corpo = await _criar_token(
        client, user, expires_at=datetime.now(UTC) - timedelta(minutes=1)
    )
    resposta = await client.get("/api/public/v1/settings", headers=_bearer(expirado))
    assert resposta.status_code == 401
    assert "expirou" in resposta.json()["detail"]

    vivo, corpo = await _criar_token(client, user)
    await client.post(f"/api/v1/api-tokens/{corpo['id']}/revoke", headers=auth_header(user))
    revogado = await client.get("/api/public/v1/settings", headers=_bearer(vivo))
    assert revogado.status_code == 401
    assert "revogado" in revogado.json()["detail"]


async def test_escopo_faltando_diz_qual_escopo_falta(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 2: um 'acesso negado' seco obrigaria o integrador a adivinhar entre sete
    recursos qual escopo ele esqueceu."""
    user = await make_user(role=UserRole.GESTOR)
    token, _corpo = await _criar_token(client, user, scopes=["read:settings"])

    resposta = await client.get("/api/public/v1/customers", headers=_bearer(token))

    assert resposta.status_code == 403
    assert "read:customers" in resposta.json()["detail"]


async def test_allowed_ips_restringe_a_origem(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 3, e o 401 é deliberado: o IP recusado não pode aprender que o token é
    válido — isso transformaria a restrição num oráculo."""
    user = await make_user(role=UserRole.GESTOR)
    token, _corpo = await _criar_token(client, user, allowed_ips=["203.0.113.0/24"])

    resposta = await client.get("/api/public/v1/settings", headers=_bearer(token))

    assert resposta.status_code == 401
    assert "Origem" in resposta.json()["detail"]


# ------------------------------------------------------------------ limites


async def test_limite_de_get_devolve_429_com_retry_after(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    token, _corpo = await _criar_token(client, user)

    ultimo = None
    for _chamada in range(GET_LIMIT_PER_MINUTE + 1):
        ultimo = await client.get("/api/public/v1/settings", headers=_bearer(token))

    assert ultimo is not None
    assert ultimo.status_code == 429
    assert int(ultimo.headers["Retry-After"]) > 0
    assert ultimo.headers["X-RateLimit-Remaining"] == "0"


async def test_headers_de_limite_em_toda_resposta(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 5: o integrador precisa saber quanto falta ANTES de bater no teto."""
    user = await make_user(role=UserRole.GESTOR)
    token, _corpo = await _criar_token(client, user)

    resposta = await client.get("/api/public/v1/settings", headers=_bearer(token))

    assert resposta.status_code == 200
    assert resposta.headers["X-RateLimit-Limit"] == str(GET_LIMIT_PER_MINUTE)
    assert resposta.headers["X-RateLimit-Remaining"] == str(GET_LIMIT_PER_MINUTE - 1)
    assert int(resposta.headers["X-RateLimit-Reset"]) > 0


async def test_limite_e_por_rota(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """'500 POST/dia por rota': um script que cria clientes não pode consumir a cota de
    quem cria processos."""
    user = await make_user(role=UserRole.GESTOR)
    token, _corpo = await _criar_token(client, user)

    for _chamada in range(GET_LIMIT_PER_MINUTE):
        await client.get("/api/public/v1/settings", headers=_bearer(token))
    outra_rota = await client.get("/api/public/v1/customers", headers=_bearer(token))

    assert outra_rota.status_code == 200
    assert outra_rota.headers["X-RateLimit-Remaining"] == str(GET_LIMIT_PER_MINUTE - 1)


# --------------------------------------------------------------- isolamento


async def test_token_de_um_escritorio_nao_le_dado_do_outro(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """O teste que carrega a spec. Um token vive fora do prédio: se ele lesse dado de
    outro escritório, o vazamento seria silencioso e permanente."""
    dono = await make_user(role=UserRole.GESTOR)
    vizinho = await make_user(role=UserRole.GESTOR)
    origem = await _create_origin(client, _auth_header(dono), "Origem do dono")
    criado = await client.post(
        "/api/v1/customers",
        json={"name": "Cliente Sigiloso", "type": "PF", "origin_id": origem},
        headers=auth_header(dono),
    )
    assert criado.status_code == 201
    token_do_vizinho, _corpo = await _criar_token(client, vizinho)

    listagem = await client.get("/api/public/v1/customers", headers=_bearer(token_do_vizinho))
    direto = await client.get(
        f"/api/public/v1/customers/{criado.json()['id']}",
        headers=_bearer(token_do_vizinho),
    )

    assert listagem.status_code == 200
    assert all(item["name"] != "Cliente Sigiloso" for item in listagem.json()["items"])
    assert direto.status_code == 404, "para quem não tem acesso, o registro não existe"


# ----------------------------------------------------------------- escrita


async def test_escrita_respeita_as_validacoes_do_service(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 10: sem atalho. CPF duplicado reprova o integrador como reprova a tela."""
    user = await make_user(role=UserRole.GESTOR)
    origem = await _create_origin(client, _auth_header(user), "Origem da API")
    token, _corpo = await _criar_token(client, user)
    payload = {
        "name": "Cliente da API",
        "origin_id": origem,
        "type": "PF",
        "identification": "11144477735",
    }

    primeiro = await client.post("/api/public/v1/customers", json=payload, headers=_bearer(token))
    segundo = await client.post(
        "/api/public/v1/customers", json={**payload, "name": "Outro"}, headers=_bearer(token)
    )

    assert primeiro.status_code == 201, primeiro.text
    assert segundo.status_code == 409, "o mesmo CPF não entra duas vezes"


async def test_erro_vem_em_rfc7807(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 7: o mesmo formato da API interna — quem integra não precisa de um segundo
    tratador de erro."""
    user = await make_user(role=UserRole.GESTOR)
    token, _corpo = await _criar_token(client, user)

    resposta = await client.get(f"/api/public/v1/customers/{uuid.uuid4()}", headers=_bearer(token))

    assert resposta.status_code == 404
    assert resposta.headers["content-type"].startswith("application/problem+json")
    corpo = resposta.json()
    assert corpo["status"] == 404
    assert corpo["title"] and corpo["detail"]


# ---------------------------------------------------------------- paginação


async def test_paginacao_por_cursor_respeita_o_limite(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    origem = await _create_origin(client, _auth_header(user), "Origem paginada")
    token, _corpo = await _criar_token(client, user)
    for indice in range(3):
        await client.post(
            "/api/public/v1/customers",
            json={"name": f"Cliente {indice}", "origin_id": origem, "type": "PF"},
            headers=_bearer(token),
        )

    primeira = await client.get("/api/public/v1/customers?limit=2", headers=_bearer(token))
    assert primeira.status_code == 200
    assert len(primeira.json()["items"]) == 2
    cursor = primeira.json()["next_cursor"]
    assert cursor

    segunda = await client.get(
        f"/api/public/v1/customers?limit=2&cursor={cursor}", headers=_bearer(token)
    )
    assert segunda.status_code == 200
    primeiros_ids = {item["id"] for item in primeira.json()["items"]}
    assert not (primeiros_ids & {item["id"] for item in segunda.json()["items"]})

    acima_do_teto = await client.get("/api/public/v1/customers?limit=1001", headers=_bearer(token))
    assert acima_do_teto.status_code == 422, "limite máximo é 1.000 (regra 8)"


# ---------------------------------------------------------------------- log


async def test_requisicao_e_registrada(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 9: é o que responde 'por que meu script parou às 3h da manhã?'."""
    user = await make_user(role=UserRole.GESTOR)
    token, corpo = await _criar_token(client, user)

    await client.get("/api/public/v1/settings", headers=_bearer(token))

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        registros = list((await session.scalars(select(ApiRequest))).all())
        guardado = await session.get(ApiToken, uuid.UUID(corpo["id"]))

    assert len(registros) == 1
    assert registros[0].path == "/api/public/v1/settings"
    assert registros[0].status_code == 200
    assert registros[0].duration_ms is not None
    assert guardado is not None and guardado.last_used_at is not None


async def test_erro_tambem_e_registrado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A requisição que falhou é a que mais interessa registrar — por isso o log usa
    sessão própria, e não a da requisição que acabou de dar rollback."""
    user = await make_user(role=UserRole.GESTOR)
    token, _corpo = await _criar_token(client, user, scopes=["read:settings"])

    await client.get("/api/public/v1/customers", headers=_bearer(token))

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        registros = list((await session.scalars(select(ApiRequest))).all())
    assert [registro.status_code for registro in registros] == [403]


# --------------------------------------------------------------- gestão


async def test_token_e_exibido_uma_vez_so(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 1: o que fica guardado é o hash. Uma listagem que devolvesse o token o
    faria vazar em log de proxy, print de tela e cache de navegador."""
    user = await make_user(role=UserRole.GESTOR)
    token, corpo = await _criar_token(client, user)
    assert token.startswith("rito_")

    listagem = await client.get("/api/v1/api-tokens", headers=auth_header(user))

    assert listagem.status_code == 200
    linha = next(item for item in listagem.json()["items"] if item["id"] == corpo["id"])
    assert linha["token"] is None
    assert linha["prefix"] == token[:8]


async def test_decimo_primeiro_token_e_recusado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 14: token esquecido é credencial viva que ninguém rotaciona."""
    user = await make_user(role=UserRole.GESTOR)
    for _indice in range(MAX_ACTIVE_TOKENS):
        await _criar_token(client, user, scopes=["read:settings"])

    resposta = await client.post(
        "/api/v1/api-tokens",
        json={"name": "Mais um", "scopes": ["read:settings"], "allowed_ips": []},
        headers=auth_header(user),
    )

    assert resposta.status_code == 422
    assert "10 tokens ativos" in resposta.json()["detail"]


async def test_escopo_desconhecido_e_recusado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)

    resposta = await client.post(
        "/api/v1/api-tokens",
        json={"name": "Token amplo", "scopes": ["write:tudo"], "allowed_ips": []},
        headers=auth_header(user),
    )

    assert resposta.status_code == 422
    assert "write:tudo" in resposta.json()["detail"]


# --------------------------------------------------- aniversariantes (dívida 34)


async def _criar_contato(
    client: AsyncClient, user: SeededUser, *, nome: str, nascimento: date
) -> None:
    """Contato com data de nascimento. O ANO não importa — a regra 6 compara mês e dia."""
    origem = await client.post(
        "/api/v1/customer-origins", json={"name": f"Origem {nome}"}, headers=auth_header(user)
    )
    assert origem.status_code == 201, origem.text
    resposta = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": nome,
            "origin_id": origem.json()["id"],
            "birthdate": nascimento.isoformat(),
        },
        headers=auth_header(user),
    )
    assert resposta.status_code == 201, resposta.text


async def test_aniversariantes_do_mes_nao_devolve_o_escritorio_inteiro(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Dívida 34: a rota devolvia os primeiros 1.000 contatos, não os aniversariantes.

    O filtro só reconhecia `"day"` e `"month"`, e a rota mandava `"month:<n>"` — nenhuma
    condição era aplicada. Este teste é o que faltava: a rota pública só tinha prova de que
    EXISTE (`test_public_api_contract.py`), nunca de que filtra.
    """
    user = await make_user(role=UserRole.GESTOR)
    token, _ = await _criar_token(client, user)
    hoje = Clock(DEFAULT_TIMEZONE).today()
    # Um mês de distância em cada sentido: nem o anterior nem o seguinte podem aparecer,
    # e usar só um dos dois deixaria passar um erro de fronteira em dezembro/janeiro.
    outro_mes = date(1990, 1 if hoje.month != 1 else 7, 15)

    await _criar_contato(client, user, nome="Aniversariante", nascimento=hoje.replace(year=1990))
    await _criar_contato(client, user, nome="Nasceu Noutro Mes", nascimento=outro_mes)

    resposta = await client.get("/api/public/v1/customers/birthdays", headers=_bearer(token))

    assert resposta.status_code == 200, resposta.text
    nomes = {item["name"] for item in resposta.json()["items"]}
    assert "Aniversariante" in nomes
    assert "Nasceu Noutro Mes" not in nomes


async def test_aniversariantes_respeita_o_mes_pedido(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Dívida 34, segundo defeito: o parâmetro `month` era decorativo.

    Mesmo que o valor casasse, o filtro comparava com `today.month` — pedir dezembro em
    setembro devolvia os de setembro. Aqui o mês pedido é sempre diferente do corrente.
    """
    user = await make_user(role=UserRole.GESTOR)
    token, _ = await _criar_token(client, user)
    hoje = Clock(DEFAULT_TIMEZONE).today()
    pedido = 1 if hoje.month != 1 else 7

    await _criar_contato(client, user, nome="Do Mes Pedido", nascimento=date(1990, pedido, 15))
    await _criar_contato(client, user, nome="Do Mes Corrente", nascimento=hoje.replace(year=1990))

    resposta = await client.get(
        "/api/public/v1/customers/birthdays", params={"month": pedido}, headers=_bearer(token)
    )

    assert resposta.status_code == 200, resposta.text
    nomes = {item["name"] for item in resposta.json()["items"]}
    assert "Do Mes Pedido" in nomes
    assert "Do Mes Corrente" not in nomes

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
from app.domain.users.models import FinancialAccess, UserRole
from app.public.deps import FAILED_AUTH_LIMIT_PER_MINUTE, GET_LIMIT_PER_MINUTE
from tests.clock import hoje
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_customers import _create_origin
from tests.integration.test_lawsuits import _auth_header, _create_stage
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_post, _create_task_type
from tests.integration.test_transactions import _fixtures, _make_gestor_full, _receita_payload

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


async def _gestor(make_user: Callable[..., Awaitable[SeededUser]], **extra: Any) -> SeededUser:
    """O emissor padrão destes testes.

    `financial_access=FULL` deixou de ser detalhe na spec 134: `TODOS_OS_ESCOPOS` inclui
    `read:transactions` e `write:transactions`, e emitir token com escopo financeiro passou
    a exigir o acesso financeiro correspondente — o token delega o que o dono tem, não
    cria autoridade nova. Sem isto, a emissão é 403, que é exatamente a regra nova.
    """
    return await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL, **extra)


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
    user = await _gestor(make_user)
    token, _corpo = await _criar_token(client, user)

    resposta = await client.get("/api/public/v1/settings", headers=_bearer(token))

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["tenant_id"] == str(user.tenant_id)
    assert any(item["id"] == str(user.user_id) for item in resposta.json()["users"])


async def test_token_ausente_invalido_expirado_e_revogado_dao_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await _gestor(make_user)

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
    user = await _gestor(make_user)
    token, _corpo = await _criar_token(client, user, scopes=["read:settings"])

    resposta = await client.get("/api/public/v1/customers", headers=_bearer(token))

    assert resposta.status_code == 403
    assert "read:customers" in resposta.json()["detail"]


async def test_allowed_ips_restringe_a_origem(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 3, e o 401 é deliberado: o IP recusado não pode aprender que o token é
    válido — isso transformaria a restrição num oráculo."""
    user = await _gestor(make_user)
    token, _corpo = await _criar_token(client, user, allowed_ips=["203.0.113.0/24"])

    resposta = await client.get("/api/public/v1/settings", headers=_bearer(token))

    assert resposta.status_code == 401
    assert "Origem" in resposta.json()["detail"]


# ------------------------------------------------------------------ limites


async def test_limite_de_get_devolve_429_com_retry_after(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)
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
    dono = await _gestor(make_user)
    vizinho = await _gestor(make_user)
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
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)

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
    user = await _gestor(make_user)
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
    user = await _gestor(make_user)
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


# ------------------------------------------------------ spec 134: mesmas regras


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def test_tarefa_privada_nao_sai_pela_api_publica(
    client: AsyncClient, factory: LawsuitFactory, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 134, regra 1. A privacidade de tarefa (033, regra 8) é um controle desenhado
    para ser inviolável até por GESTOR, e a API pública o desfazia: um `read:posts` lia
    `comments` — o corpo da tarefa — de toda tarefa privada do escritório.

    O que o token enxerga é o que enxerga QUEM O EMITIU: a privada dele aparece, a do
    colega não.
    """
    colaborador = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    lawsuit_id = await factory.create()
    tipo = await _create_task_type(client, factory.headers)

    do_colega = await _create_post(
        client,
        _auth_header(colaborador),
        lawsuit_id=lawsuit_id,
        task_type_id=tipo,
        user_ids=[str(colaborador.user_id)],
        is_private=True,
        comments="SEGREDO DO COLABORADOR",
    )
    minha = await _create_post(
        client,
        factory.headers,
        lawsuit_id=lawsuit_id,
        task_type_id=tipo,
        user_ids=[str(factory.gestor.user_id)],
        is_private=True,
        comments="Segredo de quem emitiu o token",
    )
    publica = await _create_post(
        client,
        factory.headers,
        lawsuit_id=lawsuit_id,
        task_type_id=await _create_task_type(client, factory.headers),
        user_ids=[str(factory.gestor.user_id)],
    )

    token, _corpo = await _criar_token(client, factory.gestor, scopes=["read:posts"])
    resposta = await client.get("/api/public/v1/posts", headers=_bearer(token))

    assert resposta.status_code == 200, resposta.text
    ids = {item["id"] for item in resposta.json()["items"]}
    assert do_colega["id"] not in ids, "tarefa privada de terceiro não sai pela API pública"
    assert {minha["id"], publica["id"]} <= ids
    assert "SEGREDO DO COLABORADOR" not in resposta.text


async def test_token_de_usuario_desativado_nao_autentica(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 134, regra 4: o advogado desligado às 18h não cria contato às 19h.

    O token age em nome de quem o emitiu; sem esta checagem, o offboarding fechava a
    sessão do funcionário e deixava a credencial dele viva por tempo indeterminado.
    """
    dono = await _gestor(make_user)
    outro = await make_user(tenant_id=dono.tenant_id, role=UserRole.GESTOR)
    origem = await _create_origin(client, _auth_header(dono), "Origem do desligado")
    token, _corpo = await _criar_token(client, dono)

    antes = await client.get("/api/public/v1/settings", headers=_bearer(token))
    assert antes.status_code == 200

    desativado = await client.post(
        f"/api/v1/users/{dono.user_id}/deactivate", headers=auth_header(outro)
    )
    assert desativado.status_code == 204

    leitura = await client.get("/api/public/v1/settings", headers=_bearer(token))
    escrita = await client.post(
        "/api/public/v1/customers",
        json={"name": "Cliente de quem já saiu", "origin_id": origem, "type": "PF"},
        headers=_bearer(token),
    )

    assert leitura.status_code == 401
    assert "não está mais ativo" in leitura.json()["detail"]
    assert escrita.status_code == 401


async def test_falha_de_autenticacao_e_registrada_e_tem_teto(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Spec 134, regra 5. Duas coisas que faltavam no 401 da API pública: o registro (o
    uso de um token REVOGADO é o sinal de credencial vazada, e ele sumia) e o teto (sem
    ele, adivinhar token é de graça)."""
    user = await _gestor(make_user)
    vivo, corpo = await _criar_token(client, user)
    await client.post(f"/api/v1/api-tokens/{corpo['id']}/revoke", headers=auth_header(user))

    revogado = await client.get("/api/public/v1/settings", headers=_bearer(vivo))
    assert revogado.status_code == 401

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        registros = list((await session.scalars(select(ApiRequest))).all())
    assert [registro.status_code for registro in registros] == [401]

    ultimo = None
    for _tentativa in range(FAILED_AUTH_LIMIT_PER_MINUTE + 2):
        ultimo = await client.get(
            "/api/public/v1/settings", headers=_bearer(f"rito_chute{uuid.uuid4().hex}")
        )
    assert ultimo is not None
    assert ultimo.status_code == 429, "força bruta de token não pode sair de graça"
    assert int(ultimo.headers["Retry-After"]) > 0

    # E o teto vale para a ORIGEM, não para o token: enquanto a janela não vira, nem
    # credencial boa passa daquele IP. É deliberado — o contador existe para o pedido
    # NÃO chegar ao banco, e escolher pelo token exigiria consultá-lo antes. Conta só
    # falha, então quem não erra nunca o alimenta; a janela é de um minuto.
    bom, _outro = await _criar_token(client, user)
    assert (await client.get("/api/public/v1/settings", headers=_bearer(bom))).status_code == 429


async def test_put_publico_de_lancamento_passa_pelo_service(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Spec 134, regra 6 (regra 10 da 095, cumprida). A MESMA data no MESMO lançamento
    dava 422 pela tela e 200 por aqui — o `FuturePaymentDateError` mora no service, e o
    service não era chamado."""
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, _despesa, centro_id, conta, _outra = await _fixtures(client, headers)
    criada = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(category_id=receita_id, cost_center_id=centro_id, account_id=conta),
        headers=headers,
    )
    assert criada.status_code == 201, criada.text
    lancamento = criada.json()["id"]
    token, _corpo = await _criar_token(
        client, gestor, scopes=["read:transactions", "write:transactions"]
    )
    futuro = (hoje() + timedelta(days=365)).isoformat()

    recusado = await client.put(
        f"/api/public/v1/transactions/{lancamento}",
        json={"payment_date": futuro},
        headers=_bearer(token),
    )
    aceito = await client.put(
        f"/api/public/v1/transactions/{lancamento}",
        json={"description": "acordo trabalhista"},
        headers=_bearer(token),
    )

    assert recusado.status_code == 422, recusado.text
    assert "futuro" in recusado.json()["detail"]
    assert aceito.status_code == 200, aceito.text
    # Maiúsculas é regra do service (spec 056, regra 4): sair assim prova que ele rodou.
    assert aceito.json()["description"] == "ACORDO TRABALHISTA"
    conferido = await client.get(
        f"/api/public/v1/transactions/{lancamento}", headers=_bearer(token)
    )
    assert conferido.status_code == 200
    assert conferido.json()["payment_date"] is None, "a baixa no futuro não entrou"


async def test_put_publico_de_processo_passa_pelo_service(
    client: AsyncClient, factory: LawsuitFactory
) -> None:
    """Spec 134, regra 6. O PUT público escrevia `setattr` no modelo: valor negativo
    entrava, etapa inexistente virava erro de banco."""
    lawsuit_id = await factory.create()
    outra_etapa = await _create_stage(client, factory.headers)
    token, _corpo = await _criar_token(
        client, factory.gestor, scopes=["read:lawsuits", "write:lawsuits"]
    )

    negativo = await client.put(
        f"/api/public/v1/lawsuits/{lawsuit_id}",
        json={"case_value": "-1.00"},
        headers=_bearer(token),
    )
    etapa_inexistente = await client.put(
        f"/api/public/v1/lawsuits/{lawsuit_id}",
        json={"stage_id": str(uuid.uuid4())},
        headers=_bearer(token),
    )
    movido = await client.put(
        f"/api/public/v1/lawsuits/{lawsuit_id}",
        json={"stage_id": outra_etapa, "folder": "PASTA-134"},
        headers=_bearer(token),
    )

    assert negativo.status_code == 422, negativo.text
    assert etapa_inexistente.status_code == 422, etapa_inexistente.text
    assert etapa_inexistente.json()["detail"] == "Etapa não encontrada."
    assert movido.status_code == 200, movido.text
    assert movido.json()["folder"] == "PASTA-134"

    historico = await client.get(
        f"/api/public/v1/lawsuits/{lawsuit_id}/history", headers=_bearer(token)
    )
    assert [item["to_stage_id"] for item in historico.json()] == [outra_etapa]

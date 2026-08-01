import io
from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from PIL import Image

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser

_VALID_CNPJ = "11.222.333/0001-81"
_VALID_CEP = "01310-100"


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Escritório Modelo Ltda",
        "alternate_name": "Escritório Modelo",
        "identification": _VALID_CNPJ,
        "country": "BRASIL",
        "state": "SP",
        "city": "São Paulo",
        "postal_code": _VALID_CEP,
        "street": "Av. Paulista, 1000",
        "region": "Bela Vista",
        "cellphone": "11999998888",
        "phone": "1130004000",
        "email": "contato@escritoriomodelo.com.br",
        "email_admin": "financeiro@escritoriomodelo.com.br",
        "site": "https://escritoriomodelo.com.br",
        "timezone": "America/Sao_Paulo",
    }
    payload.update(overrides)
    return payload


async def test_get_retorna_404_antes_de_qualquer_put(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user()

    response = await client.get("/api/v1/account", headers=_auth_header(seeded))

    assert response.status_code == 404


async def test_put_cria_e_get_le_de_volta(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(seeded)

    put_response = await client.put("/api/v1/account", json=_valid_payload(), headers=headers)
    assert put_response.status_code == 200
    put_body = put_response.json()
    assert put_body["name"] == "Escritório Modelo Ltda"
    # Regra 1: CNPJ armazenado sem máscara.
    assert put_body["identification"] == "11222333000181"
    assert put_body["logo_url"] is None

    get_response = await client.get("/api/v1/account", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == put_body["id"]

    # Segundo PUT é update, não um segundo registro.
    second_put = await client.put(
        "/api/v1/account", json=_valid_payload(alternate_name="Novo Nome Fantasia"), headers=headers
    )
    assert second_put.status_code == 200
    assert second_put.json()["id"] == put_body["id"]
    assert second_put.json()["alternate_name"] == "Novo Nome Fantasia"


async def test_cnpj_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.GESTOR)

    response = await client.put(
        "/api/v1/account",
        json=_valid_payload(identification="11.222.333/0001-82"),
        headers=_auth_header(seeded),
    )

    assert response.status_code == 422


async def test_colaborador_recebe_403_no_put(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.COLABORADOR)

    response = await client.put(
        "/api/v1/account", json=_valid_payload(), headers=_auth_header(seeded)
    )

    assert response.status_code == 403


async def test_colaborador_consegue_ler(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    await client.put("/api/v1/account", json=_valid_payload(), headers=_auth_header(gestor))

    colaborador = await make_user(tenant_id=gestor.tenant_id, role=UserRole.COLABORADOR)
    response = await client.get("/api/v1/account", headers=_auth_header(colaborador))

    assert response.status_code == 200


async def test_timezone_fora_da_lista_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.GESTOR)

    response = await client.put(
        "/api/v1/account",
        json=_valid_payload(timezone="America/New_York"),
        headers=_auth_header(seeded),
    )

    assert response.status_code == 422


async def test_cep_fora_do_formato_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.GESTOR)

    response = await client.put(
        "/api/v1/account",
        json=_valid_payload(postal_code="01310100"),
        headers=_auth_header(seeded),
    )

    assert response.status_code == 422


async def test_upload_de_logo_sem_conta_configurada_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.GESTOR)

    response = await client.post(
        "/api/v1/account/logo",
        files={"file": ("logo.png", b"\x89PNG\r\nqualquer coisa", "image/png")},
        headers=_auth_header(seeded),
    )

    assert response.status_code == 404


async def test_tenant_a_nao_le_account_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    tenant_a = await make_user(role=UserRole.GESTOR)
    tenant_b = await make_user(role=UserRole.GESTOR)

    await client.put(
        "/api/v1/account",
        json=_valid_payload(name="Escritório A"),
        headers=_auth_header(tenant_a),
    )

    # Tenant B nunca configurou a própria conta — RLS impede que ele veja a de A,
    # mesmo que A já exista no banco.
    response = await client.get("/api/v1/account", headers=_auth_header(tenant_b))

    assert response.status_code == 404


async def test_upload_de_logo_acima_de_2mb_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(seeded)
    await client.put("/api/v1/account", json=_valid_payload(), headers=headers)

    oversized_content = b"\x89PNG\r\n" + (b"0" * (2 * 1024 * 1024 + 1))
    response = await client.post(
        "/api/v1/account/logo",
        files={"file": ("logo.png", oversized_content, "image/png")},
        headers=headers,
    )

    assert response.status_code == 422


async def test_upload_de_logo_valido_redimensiona_e_retorna_url(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(seeded)
    await client.put("/api/v1/account", json=_valid_payload(), headers=headers)

    buffer = io.BytesIO()
    Image.new("RGB", (1000, 1000), color="red").save(buffer, format="PNG")

    response = await client.post(
        "/api/v1/account/logo",
        files={"file": ("logo.png", buffer.getvalue(), "image/png")},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["logo_url"] is not None

    get_response = await client.get("/api/v1/account", headers=headers)
    assert get_response.json()["logo_url"] is not None

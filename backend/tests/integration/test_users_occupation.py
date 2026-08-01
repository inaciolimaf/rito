import io
import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from PIL import Image

from app.core.tokens import create_access_token
from app.domain.users.models import UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


async def test_lista_as_67_ocupacoes(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user()

    response = await client.get("/api/v1/occupations", headers=_auth_header(seeded))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 67
    assert {"id": 1, "name": "Advogado Gestor"} in body


async def test_cargo_de_advogado_sem_oab_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    colaborador = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    response = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json={
            "name": "Advogado Sem OAB",
            "role": "COLABORADOR",
            "financial_access": "NONE",
            "occupation_id": 1,  # Advogado Gestor
        },
        headers=_auth_header(administrador),
    )

    assert response.status_code == 422


async def test_cargo_de_advogado_com_oab_funciona(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    colaborador = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    response = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json={
            "name": "Advogado Com OAB",
            "role": "COLABORADOR",
            "financial_access": "NONE",
            "occupation_id": 1,
            "number_oab": "123456/SP",
        },
        headers=_auth_header(administrador),
    )

    assert response.status_code == 200
    assert response.json()["number_oab"] == "123456/SP"


async def test_cargo_que_nao_e_de_advogado_nao_exige_oab(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    colaborador = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    response = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json={
            "name": "Recepcionista",
            "role": "COLABORADOR",
            "financial_access": "NONE",
            "occupation_id": 24,  # Recepcionista
        },
        headers=_auth_header(administrador),
    )

    assert response.status_code == 200


async def test_upload_de_avatar_valido(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.COLABORADOR)
    buffer = io.BytesIO()
    Image.new("RGB", (800, 800), color="green").save(buffer, format="PNG")

    response = await client.post(
        f"/api/v1/users/{seeded.user_id}/avatar",
        files={"file": ("avatar.png", buffer.getvalue(), "image/png")},
        headers=_auth_header(seeded),
    )

    assert response.status_code == 200
    assert response.json()["avatar_url"] is not None


async def test_upload_de_avatar_com_conteudo_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.COLABORADOR)

    response = await client.post(
        f"/api/v1/users/{seeded.user_id}/avatar",
        files={"file": ("avatar.png", b"isso nao e uma imagem", "image/png")},
        headers=_auth_header(seeded),
    )

    assert response.status_code == 422


async def test_upload_de_avatar_para_usuario_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.post(
        f"/api/v1/users/{uuid.uuid4()}/avatar",
        files={"file": ("avatar.png", b"conteudo", "image/png")},
        headers=_auth_header(administrador),
    )

    assert response.status_code == 404


async def test_upload_de_avatar_de_outro_usuario_sem_ser_administrador_retorna_403(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador_a = await make_user(role=UserRole.COLABORADOR)
    colaborador_b = await make_user(tenant_id=colaborador_a.tenant_id, role=UserRole.COLABORADOR)

    response = await client.post(
        f"/api/v1/users/{colaborador_b.user_id}/avatar",
        files={"file": ("avatar.png", b"conteudo", "image/png")},
        headers=_auth_header(colaborador_a),
    )

    assert response.status_code == 403

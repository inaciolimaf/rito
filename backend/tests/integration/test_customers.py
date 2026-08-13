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


async def _create_origin(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    response = await client.post("/api/v1/customer-origins", json={"name": name}, headers=headers)
    assert response.status_code == 201
    result: str = response.json()["id"]
    return result


def _png_bytes(size: tuple[int, int] = (800, 800)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color="blue").save(buffer, format="PNG")
    return buffer.getvalue()


async def test_crud_pf_completo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Indicação")

    create_response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Maria da Silva",
            "origin_id": origin_id,
            "identification": "11144477735",
            "document": "1234567",
            "birthdate": "1990-05-20",
            "gender": "F",
            "cellphone": "11999998888",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["type"] == "PF"
    assert body["name"] == "Maria da Silva"
    assert body["gender"] == "F"
    customer_id = body["id"]

    get_response = await client.get(f"/api/v1/customers/{customer_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["identification"] == "11144477735"

    update_response = await client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "type": "PF",
            "name": "Maria da Silva Santos",
            "origin_id": origin_id,
            "gender": "F",
        },
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Maria da Silva Santos"


async def test_crud_pj_completo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Site do Escritório")

    create_response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PJ",
            "name": "Empresa Exemplo LTDA",
            "origin_id": origin_id,
            "identification": "11222333000181",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    body = create_response.json()
    assert body["type"] == "PJ"
    customer_id = body["id"]

    update_response = await client.put(
        f"/api/v1/customers/{customer_id}",
        json={"type": "PJ", "name": "Empresa Exemplo S.A.", "origin_id": origin_id},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Empresa Exemplo S.A."


async def test_sem_origem_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Sem Origem"},
        headers=_auth_header(gestor),
    )

    assert response.status_code == 422


async def test_cpf_duplicado_no_tenant_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Escritório")

    await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Primeiro",
            "origin_id": origin_id,
            "identification": "12345678909",
        },
        headers=headers,
    )
    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Segundo",
            "origin_id": origin_id,
            "identification": "12345678909",
        },
        headers=headers,
    )

    assert response.status_code == 409


async def test_renomear_identification_para_uma_ja_usada_retorna_409(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Primeiro",
            "origin_id": origin_id,
            "identification": "11144477735",
        },
        headers=headers,
    )
    second = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Segundo",
            "origin_id": origin_id,
            "identification": "98765432100",
        },
        headers=headers,
    )
    second_id = second.json()["id"]

    response = await client.put(
        f"/api/v1/customers/{second_id}",
        json={
            "type": "PF",
            "name": "Segundo",
            "origin_id": origin_id,
            "identification": "11144477735",
        },
        headers=headers,
    )

    assert response.status_code == 409


async def test_mesmo_cpf_em_outro_tenant_e_aceito(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_a = await make_user(role=UserRole.GESTOR)
    gestor_b = await make_user(role=UserRole.GESTOR)
    headers_a = _auth_header(gestor_a)
    headers_b = _auth_header(gestor_b)
    origin_a = await _create_origin(client, headers_a, "Origem A")
    origin_b = await _create_origin(client, headers_b, "Origem B")

    response_a = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Cliente A",
            "origin_id": origin_a,
            "identification": "11122233396",
        },
        headers=headers_a,
    )
    response_b = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Cliente B",
            "origin_id": origin_b,
            "identification": "11122233396",
        },
        headers=headers_b,
    )

    assert response_a.status_code == 201
    assert response_b.status_code == 201


async def test_dois_contatos_sem_identification_coexistem(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    first = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Sem Documento 1", "origin_id": origin_id},
        headers=headers,
    )
    second = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Sem Documento 2", "origin_id": origin_id},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["identification"] is None
    assert second.json()["identification"] is None


async def test_representante_sem_nome_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Cliente Com Representante",
            "origin_id": origin_id,
            "has_representative": True,
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_representante_com_nome_e_aceito(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Cliente Com Representante",
            "origin_id": origin_id,
            "has_representative": True,
            "rep_name": "Representante Legal",
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["rep_name"] == "Representante Legal"


async def test_delete_arquiva_em_vez_de_apagar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    admin = await make_user(role=UserRole.ADMINISTRADOR, tenant_id=gestor.tenant_id)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    create_response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Cliente Arquivado", "origin_id": origin_id},
        headers=headers,
    )
    customer_id = create_response.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/customers/{customer_id}", headers=_auth_header(admin)
    )
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/v1/customers/{customer_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["is_archived"] is True


async def test_colaborador_recebe_403_ao_arquivar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    colaborador = await make_user(role=UserRole.COLABORADOR, tenant_id=gestor.tenant_id)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    create_response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Cliente", "origin_id": origin_id},
        headers=headers,
    )
    customer_id = create_response.json()["id"]

    response = await client.delete(
        f"/api/v1/customers/{customer_id}", headers=_auth_header(colaborador)
    )

    assert response.status_code == 403


async def test_tenant_a_nao_ve_contato_de_tenant_b(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor_a = await make_user(role=UserRole.GESTOR)
    gestor_b = await make_user(role=UserRole.GESTOR)
    headers_a = _auth_header(gestor_a)
    origin_id = await _create_origin(client, headers_a, "Origem")

    create_response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Isolado", "origin_id": origin_id},
        headers=headers_a,
    )
    customer_id = create_response.json()["id"]

    response = await client.get(f"/api/v1/customers/{customer_id}", headers=_auth_header(gestor_b))

    assert response.status_code == 404


async def test_get_contato_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.get(f"/api/v1/customers/{uuid.uuid4()}", headers=_auth_header(gestor))

    assert response.status_code == 404


async def test_put_contato_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.put(
        f"/api/v1/customers/{uuid.uuid4()}",
        json={"type": "PF", "name": "Não Existe", "origin_id": origin_id},
        headers=headers,
    )

    assert response.status_code == 404


async def test_delete_contato_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    admin = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.delete(f"/api/v1/customers/{uuid.uuid4()}", headers=_auth_header(admin))

    assert response.status_code == 404


async def test_gender_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Cliente",
            "origin_id": origin_id,
            "gender": "X",
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_pj_limpa_campos_exclusivos_de_pf(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    create_response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Vira PJ",
            "origin_id": origin_id,
            "birthdate": "1990-01-01",
            "gender": "F",
            "occupation": "Advogada",
        },
        headers=headers,
    )
    customer_id = create_response.json()["id"]

    update_response = await client.put(
        f"/api/v1/customers/{customer_id}",
        json={
            "type": "PJ",
            "name": "Vira PJ LTDA",
            "origin_id": origin_id,
            "birthdate": "1990-01-01",
            "gender": "F",
            "occupation": "Advogada",
        },
        headers=headers,
    )

    assert update_response.status_code == 200
    body = update_response.json()
    assert body["birthdate"] is None
    assert body["gender"] is None
    assert body["occupation"] is None


async def test_upload_foto_valida_e_redimensiona(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    create_response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Com Foto", "origin_id": origin_id},
        headers=headers,
    )
    customer_id = create_response.json()["id"]

    response = await client.post(
        f"/api/v1/customers/{customer_id}/photo",
        files={"file": ("foto.png", _png_bytes(), "image/png")},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["photo_url"] is not None


async def test_upload_foto_formato_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    create_response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Sem Foto", "origin_id": origin_id},
        headers=headers,
    )
    customer_id = create_response.json()["id"]

    response = await client.post(
        f"/api/v1/customers/{customer_id}/photo",
        files={"file": ("foto.svg", b"<svg></svg>", "image/svg+xml")},
        headers=headers,
    )

    assert response.status_code == 422


async def test_upload_foto_acima_de_5mb_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")
    create_response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Sem Foto", "origin_id": origin_id},
        headers=headers,
    )
    customer_id = create_response.json()["id"]

    oversized = b"0" * (5 * 1024 * 1024 + 1)
    response = await client.post(
        f"/api/v1/customers/{customer_id}/photo",
        files={"file": ("foto.png", oversized, "image/png")},
        headers=headers,
    )

    assert response.status_code == 422


async def test_upload_foto_contato_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.post(
        f"/api/v1/customers/{uuid.uuid4()}/photo",
        files={"file": ("foto.png", _png_bytes(), "image/png")},
        headers=_auth_header(gestor),
    )

    assert response.status_code == 404


async def test_cpf_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 1/2 (spec 018): dígito verificador real, não só tamanho."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "CPF Errado",
            "origin_id": origin_id,
            "identification": "11144477736",
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_cpf_com_mascara_e_aceito_e_guardado_so_com_digitos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 3: máscara aceita na entrada; o banco guarda só dígitos."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Com Máscara",
            "origin_id": origin_id,
            "identification": "111.444.777-35",
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["identification"] == "11144477735"


async def test_telefone_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Telefone Com DDI",
            "origin_id": origin_id,
            "cellphone": "5511999998888",
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_telefone_valido_e_guardado_so_com_digitos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Telefone Válido",
            "origin_id": origin_id,
            "cellphone": "(11) 99999-8888",
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["cellphone"] == "11999998888"


async def test_cep_invalido_retorna_422(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "CEP Errado",
            "origin_id": origin_id,
            "postal_code": "123",
        },
        headers=headers,
    )

    assert response.status_code == 422


async def test_cep_e_normalizado_para_99999_999(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "CEP Sem Máscara",
            "origin_id": origin_id,
            "postal_code": "01310100",
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["postal_code"] == "01310-100"


async def test_campos_opcionais_vazios_sao_aceitos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """identification/cellphone/phone/postal_code explicitamente vazios (não omitidos)
    também passam — os validadores tratam string vazia como "não informado"."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Campos Vazios",
            "origin_id": origin_id,
            "identification": "",
            "cellphone": "",
            "phone": "",
            "postal_code": "",
        },
        headers=headers,
    )

    assert response.status_code == 201


async def test_representante_com_identificacao_e_cep_validos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    response = await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "Com Representante Completo",
            "origin_id": origin_id,
            "has_representative": True,
            "rep_name": "Representante Legal",
            "rep_identification": "111.444.777-35",
            "rep_postal_code": "01310100",
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["rep_identification"] == "11144477735"
    assert body["rep_postal_code"] == "01310-100"


async def test_check_duplicate_encontra_por_nome_e_nascimento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    origin_id = await _create_origin(client, headers, "Origem")

    await client.post(
        "/api/v1/customers",
        json={
            "type": "PF",
            "name": "João Duplicado",
            "origin_id": origin_id,
            "birthdate": "1985-03-10",
        },
        headers=headers,
    )

    response = await client.get(
        "/api/v1/customers/check-duplicate",
        params={"name": "joão duplicado", "birthdate": "1985-03-10"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_duplicate"] is True
    assert len(body["candidates"]) == 1


async def test_check_duplicate_sem_correspondencia(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.get(
        "/api/v1/customers/check-duplicate",
        params={"name": "Ninguém", "birthdate": "2000-01-01"},
        headers=_auth_header(gestor),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["has_duplicate"] is False
    assert body["candidates"] == []


async def test_marital_statuses_lista_as_6_opcoes(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)

    response = await client.get("/api/v1/marital-statuses", headers=_auth_header(gestor))

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert names == {
        "CASADO(A)",
        "DIVORCIADO(A)",
        "SEPARADO(A)",
        "SOLTEIRO(A)",
        "UNIÃO ESTÁVEL",
        "VIÚVO(A)",
    }


async def test_criar_contato_dispara_novo_cliente_quando_configurado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)
    rule_response = await client.put(
        "/api/v1/notification-rules/NOVO_CLIENTE",
        json={"responsible_user_id": str(gestor.user_id), "channels": []},
        headers=headers,
    )
    assert rule_response.status_code == 200, rule_response.text

    origin_id = await _create_origin(client, headers, "Indicação")
    create_response = await client.post(
        "/api/v1/customers",
        json={"type": "PF", "name": "Contato Notificado", "origin_id": origin_id},
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text

    notifications = await client.get("/api/v1/notifications", headers=headers)
    assert notifications.status_code == 200
    kinds = {item["kind"] for item in notifications.json()["items"]}
    assert "NOVO_CLIENTE" in kinds

import uuid
from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.core.tokens import create_access_token
from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser


def _auth_header(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(user_id=seeded.user_id, tenant_id=seeded.tenant_id)
    return {"Authorization": f"Bearer {token}"}


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "Nome Atualizado",
        "role": "COLABORADOR",
        "financial_access": "NONE",
        "salary": "5000.00",
    }
    payload.update(overrides)
    return payload


async def test_usuario_nao_altera_o_proprio_role(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.COLABORADOR, financial_access=FinancialAccess.NONE)

    response = await client.put(
        f"/api/v1/users/{seeded.user_id}",
        json=_valid_payload(role="ADMINISTRADOR"),
        headers=_auth_header(seeded),
    )

    assert response.status_code == 403


async def test_usuario_altera_o_proprio_nome_sem_mudar_role(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    seeded = await make_user(role=UserRole.COLABORADOR, financial_access=FinancialAccess.NONE)

    response = await client.put(
        f"/api/v1/users/{seeded.user_id}",
        json=_valid_payload(name="Nome Novo"),
        headers=_auth_header(seeded),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Nome Novo"


async def test_administrador_altera_role_de_outro_usuario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)
    colaborador = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    response = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(role="ADMINISTRADOR"),
        headers=_auth_header(administrador),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMINISTRADOR"


async def test_colaborador_nao_pode_editar_outro_usuario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador_a = await make_user(role=UserRole.COLABORADOR)
    colaborador_b = await make_user(tenant_id=colaborador_a.tenant_id, role=UserRole.COLABORADOR)

    response = await client.put(
        f"/api/v1/users/{colaborador_b.user_id}",
        json=_valid_payload(),
        headers=_auth_header(colaborador_a),
    )

    assert response.status_code == 403


async def test_salario_oculto_para_financial_access_none(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(
        role=UserRole.ADMINISTRADOR, financial_access=FinancialAccess.NONE
    )
    colaborador = await make_user(tenant_id=administrador.tenant_id, role=UserRole.COLABORADOR)

    await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(salary="12345.67"),
        headers=_auth_header(administrador),
    )

    response = await client.get(
        f"/api/v1/users/{colaborador.user_id}", headers=_auth_header(administrador)
    )

    assert response.status_code == 200
    assert response.json()["salary"] is None


async def test_get_usuario_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.get(
        f"/api/v1/users/{uuid.uuid4()}", headers=_auth_header(administrador)
    )

    assert response.status_code == 404


async def test_put_usuario_inexistente_retorna_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    administrador = await make_user(role=UserRole.ADMINISTRADOR)

    response = await client.put(
        f"/api/v1/users/{uuid.uuid4()}",
        json=_valid_payload(),
        headers=_auth_header(administrador),
    )

    assert response.status_code == 404


async def test_salario_visivel_para_financial_access_read_only(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Quem GRAVA o salário mudou na spec 135 (era este mesmo administrador READ_ONLY);
    quem LÊ, que é o que este teste afirma, continua sendo READ_ONLY. Escrever dinheiro
    exige FULL — um READ_ONLY que grava não é um READ_ONLY."""
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    administrador = await make_user(
        tenant_id=gestor.tenant_id,
        role=UserRole.ADMINISTRADOR,
        financial_access=FinancialAccess.READ_ONLY,
    )
    colaborador = await make_user(tenant_id=gestor.tenant_id, role=UserRole.COLABORADOR)

    gravou = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(salary="12345.67"),
        headers=_auth_header(gestor),
    )
    assert gravou.status_code == 200

    response = await client.get(
        f"/api/v1/users/{colaborador.user_id}", headers=_auth_header(administrador)
    )

    assert response.status_code == 200
    assert response.json()["salary"] == "12345.67"


# ---------------------------------------------------------------------------
# Spec 135, regra 1 — o corpo do PUT não é uma procuração.
#
# O `update` fazia `setattr` sobre tudo que chegasse, com uma guarda só para
# `role`/`financial_access` de si mesmo. Os testes abaixo entram pela rota do perfil
# tentando chegar a estados que outra rota protege com guarda mais estrita, que é a forma
# do defeito: as duas rotas declaram permissão, então `test_permission_coverage` vê as
# duas como cobertas.
# ---------------------------------------------------------------------------


async def _com_salario(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    *,
    salary: str,
    role: UserRole = UserRole.COLABORADOR,
    financial_access: FinancialAccess = FinancialAccess.READ_ONLY,
) -> tuple[SeededUser, SeededUser]:
    """Um gestor FULL e um subordinado com salário já gravado pelo caminho legítimo."""
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    alvo = await make_user(tenant_id=gestor.tenant_id, role=role, financial_access=financial_access)
    gravou = await client.put(
        f"/api/v1/users/{alvo.user_id}",
        json=_valid_payload(
            role=role.value, financial_access=financial_access.value, salary=salary
        ),
        headers=_auth_header(gestor),
    )
    assert gravou.status_code == 200, gravou.text
    return gestor, alvo


async def test_colaborador_nao_reescreve_o_proprio_salario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """O achado que abriu a spec: `salary` só é LEGÍVEL com acesso financeiro, e era
    GRAVÁVEL por qualquer um, em si mesmo, pela tela de perfil."""
    _gestor, colaborador = await _com_salario(client, make_user, salary="3000.00")

    resposta = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(role="COLABORADOR", financial_access="READ_ONLY", salary="99999.00"),
        headers=_auth_header(colaborador),
    )

    # A requisição passa (ela também mudou o nome, que é dele), o salário não.
    assert resposta.status_code == 200
    assert resposta.json()["salary"] == "3000.00"
    assert resposta.json()["name"] == "Nome Atualizado"


async def test_nem_com_acesso_financeiro_total_alguem_grava_o_proprio_salario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """FULL é o acesso do RH, e RH é sempre outra pessoa. O eixo financeiro autoriza
    mexer no dinheiro do escritório, não no próprio contracheque."""
    gestor, _alvo = await _com_salario(client, make_user, salary="1000.00")

    resposta = await client.put(
        f"/api/v1/users/{gestor.user_id}",
        json=_valid_payload(role="GESTOR", financial_access="FULL", salary="88888.00"),
        headers=_auth_header(gestor),
    )

    assert resposta.status_code == 200
    assert resposta.json()["salary"] is None


async def test_administrador_com_read_only_nao_grava_salario_de_subordinado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, colaborador = await _com_salario(client, make_user, salary="3000.00")
    administrador = await make_user(
        tenant_id=gestor.tenant_id,
        role=UserRole.ADMINISTRADOR,
        financial_access=FinancialAccess.READ_ONLY,
    )

    resposta = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(role="COLABORADOR", financial_access="READ_ONLY", salary="1.00"),
        headers=_auth_header(administrador),
    )

    assert resposta.status_code == 200
    assert resposta.json()["salary"] == "3000.00"


async def test_colaborador_nao_zera_a_meta_de_pontos_que_o_gestor_definiu(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """A parte mais silenciosa do defeito: `points_goal` tem default `None` no schema, e
    salvar o perfil SEM enviá-lo apagava a meta — sem erro, sem registro, sem ninguém
    tentando nada. `PUT /users/{id}/points-goal` exige GESTOR; a rota do perfil não pode
    desfazer o que ela grava."""
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.NONE)
    colaborador = await make_user(tenant_id=gestor.tenant_id, role=UserRole.COLABORADOR)

    definiu = await client.put(
        f"/api/v1/users/{colaborador.user_id}/points-goal",
        json={"points_goal": 120},
        headers=_auth_header(gestor),
    )
    assert definiu.status_code == 200
    assert definiu.json()["points_goal"] == 120

    salvou_o_perfil = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(),
        headers=_auth_header(colaborador),
    )

    assert salvou_o_perfil.status_code == 200
    assert salvou_o_perfil.json()["points_goal"] == 120


async def test_colaborador_nao_define_a_propria_meta_de_pontos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    colaborador = await make_user(role=UserRole.COLABORADOR)

    resposta = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(points_goal=999),
        headers=_auth_header(colaborador),
    )

    assert resposta.status_code == 200
    assert resposta.json()["points_goal"] is None


async def test_colaborador_nao_muda_a_propria_data_de_admissao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Dado de vínculo é do RH. O que a pessoa edita no próprio perfil é dado pessoal —
    nome, documento, telefone, OAB."""
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    colaborador = await make_user(tenant_id=gestor.tenant_id, role=UserRole.COLABORADOR)
    await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(admission_date="2020-03-01"),
        headers=_auth_header(gestor),
    )

    resposta = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(admission_date="2015-01-01", cellphone="11999998888"),
        headers=_auth_header(colaborador),
    )

    assert resposta.status_code == 200
    assert resposta.json()["admission_date"] == "2020-03-01"
    # E o que É dele muda na mesma requisição.
    assert resposta.json()["cellphone"] == "11999998888"


async def test_gestor_continua_gravando_cargo_jornada_e_salario_do_subordinado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """A lista é uma permissão, não uma proibição: quem tem o papel continua editando.

    Sem este teste, `editable_fields` devolvendo o conjunto vazio passaria em todos os
    outros — e o cadastro de pessoal pararia de funcionar em silêncio.
    """
    gestor = await make_user(role=UserRole.GESTOR, financial_access=FinancialAccess.FULL)
    colaborador = await make_user(tenant_id=gestor.tenant_id, role=UserRole.COLABORADOR)

    resposta = await client.put(
        f"/api/v1/users/{colaborador.user_id}",
        json=_valid_payload(
            role="ADMINISTRADOR",
            financial_access="READ_ONLY",
            salary="7500.00",
            admission_date="2024-02-01",
            work_start="09:00:00",
            work_end="18:00:00",
            points_goal=150,
            is_responsible=True,
        ),
        headers=_auth_header(gestor),
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["role"] == "ADMINISTRADOR"
    assert corpo["financial_access"] == "READ_ONLY"
    assert corpo["salary"] == "7500.00"
    assert corpo["admission_date"] == "2024-02-01"
    assert corpo["work_start"] == "09:00:00"
    assert corpo["points_goal"] == 150
    assert corpo["is_responsible"] is True

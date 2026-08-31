"""Spec 079 — parcerias entre escritórios.

Cinco destes testes são de VAZAMENTO entre tenants (regra 4/9): eles provam que o
parceiro enxerga o processo compartilhado e **nada mais** do escritório dono. São os
testes mais importantes do projeto — um furo aqui expõe carteira de cliente a
concorrente, então cada um verifica a ausência por uma porta diferente (listagem de
processos, contatos, financeiro, relatório).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient

from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser
from tests.integration.email_capture import capture_emails
from tests.integration.test_lawsuits import (
    _auth_header,
    _create_customer,
    _create_lawsuit,
    _create_lawsuit_type,
    _create_stage,
)
from tests.integration.test_posts import _create_task_type


@dataclass
class Scenario:
    owner: SeededUser
    owner_headers: dict[str, str]
    partner: SeededUser
    partner_headers: dict[str, str]
    partnership_id: str
    lawsuit_id: str
    task_type_id: str


async def _invite(client: AsyncClient, headers: dict[str, str], email: str) -> dict[str, Any]:
    """Convida e devolve a resposta com o `token` reposto a partir do E-MAIL.

    Desde a spec 102 (regra 19) o token não volta no corpo da resposta — ele vai no link
    do e-mail. O helper captura o envio e recoloca o token no dicionário para os testes
    seguirem lendo `invite["token"]`, agora pelo caminho por onde ele realmente passa.
    """
    with capture_emails() as canal:
        response = await client.post(
            "/api/v1/partnerships/invite", json={"email": email}, headers=headers
        )
        assert response.status_code == 201, response.text
        corpo = dict(response.json())
        assert "token" not in corpo, "regra 19: o token não pode voltar na resposta HTTP"
        corpo["token"] = canal.token_para(email)
    return corpo


async def _setup(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    *,
    owner_financial: FinancialAccess = FinancialAccess.NONE,
    partner_financial: FinancialAccess = FinancialAccess.NONE,
) -> Scenario:
    """Dois escritórios com parceria ATIVA e um processo (ainda não compartilhado) do
    lado do dono. `partner_financial` existe para a regra 9: o acesso financeiro do
    parceiro no tenant DELE não pode abrir nada do dono."""
    owner = await make_user(role=UserRole.GESTOR, financial_access=owner_financial)
    partner = await make_user(role=UserRole.GESTOR, financial_access=partner_financial)
    owner_headers = _auth_header(owner)
    partner_headers = _auth_header(partner)

    invite = await _invite(client, owner_headers, partner.email)
    accepted = await client.post(
        "/api/v1/partnerships/accept", json={"token": invite["token"]}, headers=partner_headers
    )
    assert accepted.status_code == 200, accepted.text

    type_id, _group = await _create_lawsuit_type(client, owner_headers)
    stage_id = await _create_stage(client, owner_headers)
    lawsuit = await _create_lawsuit(
        client,
        owner_headers,
        user_id=str(owner.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
        case_value=50000,
        fees_value=7500,
    )
    task_type_id = await _create_task_type(client, owner_headers)
    return Scenario(
        owner=owner,
        owner_headers=owner_headers,
        partner=partner,
        partner_headers=partner_headers,
        partnership_id=str(accepted.json()["id"]),
        lawsuit_id=str(lawsuit["id"]),
        task_type_id=task_type_id,
    )


async def _share(
    client: AsyncClient,
    scenario: Scenario,
    *,
    can_view_financial: bool = False,
    can_create_tasks: bool = True,
) -> str:
    response = await client.post(
        f"/api/v1/lawsuits/{scenario.lawsuit_id}/share",
        json={
            "partnership_id": scenario.partnership_id,
            "can_view_financial": can_view_financial,
            "can_create_tasks": can_create_tasks,
        },
        headers=scenario.owner_headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


@pytest.fixture
async def scenario(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> Scenario:
    return await _setup(client, make_user)


async def test_convite_e_aceite_ativam_a_parceria(scenario: Scenario, client: AsyncClient) -> None:
    """Regra 1: aceita uma vez, vale para os dois lados."""
    for headers, is_requester in (
        (scenario.owner_headers, True),
        (scenario.partner_headers, False),
    ):
        response = await client.get("/api/v1/partnerships", headers=headers)
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "ATIVA"
        assert items[0]["is_requester"] is is_requester
        assert items[0]["partner_name"] is not None


async def test_convite_para_email_sem_conta_fica_pendente(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 2: sem conta no Rito, é convite de cadastro e a parceria espera."""
    gestor = await make_user(role=UserRole.GESTOR)
    headers = _auth_header(gestor)

    invite = await _invite(client, headers, f"{uuid.uuid4().hex}@escritorio-novo.example.com")

    assert invite["account_exists"] is False
    partnership = invite["partnership"]
    assert partnership["status"] == "PENDENTE"
    assert partnership["partner_tenant_id"] is None


async def test_compartilhar_da_acesso_ao_processo(scenario: Scenario, client: AsyncClient) -> None:
    await _share(client, scenario)

    response = await client.get(
        "/api/v1/partnerships/shared-with-me", headers=scenario.partner_headers
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["lawsuit_id"] for item in items] == [scenario.lawsuit_id]

    detail = await client.get(
        f"/api/v1/partnerships/shared-with-me/{scenario.lawsuit_id}",
        headers=scenario.partner_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["parties"], "o parceiro precisa enxergar as partes do processo"


async def test_parceiro_nao_ve_outros_processos_do_dono(
    scenario: Scenario, client: AsyncClient
) -> None:
    """VAZAMENTO: compartilhar é por processo (regra 3) — a carteira continua invisível."""
    type_id, _group = await _create_lawsuit_type(client, scenario.owner_headers)
    stage_id = await _create_stage(client, scenario.owner_headers)
    outro = await _create_lawsuit(
        client,
        scenario.owner_headers,
        user_id=str(scenario.owner.user_id),
        lawsuit_type_id=type_id,
        stage_id=stage_id,
    )
    await _share(client, scenario)

    listing = await client.get("/api/v1/lawsuits", headers=scenario.partner_headers)
    assert listing.status_code == 200
    assert listing.json()["items"] == []

    for lawsuit_id in (scenario.lawsuit_id, str(outro["id"])):
        direct = await client.get(
            f"/api/v1/lawsuits/{lawsuit_id}", headers=scenario.partner_headers
        )
        assert direct.status_code == 404, "nem o processo compartilhado sai pela rota normal"

    shared = await client.get(
        f"/api/v1/partnerships/shared-with-me/{outro['id']}", headers=scenario.partner_headers
    )
    assert shared.status_code == 404


async def test_parceiro_nao_ve_contatos_nao_relacionados(
    scenario: Scenario, client: AsyncClient
) -> None:
    """VAZAMENTO: as partes do processo compartilhado aparecem; a agenda de contatos não."""
    await _create_customer(client, scenario.owner_headers, "Contato Sigiloso")
    await _share(client, scenario)

    response = await client.get("/api/v1/customers", headers=scenario.partner_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []


async def test_parceiro_nao_ve_financeiro_sem_permissao(
    scenario: Scenario, client: AsyncClient
) -> None:
    """VAZAMENTO (regra 9): sem `can_view_financial` o valor nem sai do banco."""
    await _share(client, scenario, can_view_financial=False)

    response = await client.get(
        "/api/v1/partnerships/shared-with-me", headers=scenario.partner_headers
    )
    item = response.json()["items"][0]
    assert item["case_value"] is None
    assert item["fees_value"] is None

    # A rota financeira do processo nem chega no RLS: o parceiro não tem
    # `financial_access` no tenant dele (403). Com acesso financeiro FULL do lado dele o
    # RLS ainda barraria (404) — as duas portas estão fechadas, e é o teste seguinte que
    # prova que só o compartilhamento abre o valor.
    summary = await client.get(
        f"/api/v1/lawsuits/{scenario.lawsuit_id}/financial-summary",
        headers=scenario.partner_headers,
    )
    assert summary.status_code in (403, 404)


async def test_parceiro_com_permissao_ve_financeiro(
    scenario: Scenario, client: AsyncClient
) -> None:
    await _share(client, scenario, can_view_financial=True)

    response = await client.get(
        "/api/v1/partnerships/shared-with-me", headers=scenario.partner_headers
    )
    item = response.json()["items"][0]
    assert item["case_value"] == 50000
    assert item["fees_value"] == 7500


async def test_parceiro_sem_can_create_tasks_recebe_403(
    scenario: Scenario, client: AsyncClient
) -> None:
    """Regra 5: sem a permissão, o compartilhamento é só leitura."""
    await _share(client, scenario, can_create_tasks=False)

    types = await client.get(
        f"/api/v1/partnerships/shared-with-me/{scenario.lawsuit_id}/task-types",
        headers=scenario.partner_headers,
    )
    assert types.status_code == 200

    response = await client.post(
        f"/api/v1/partnerships/shared-with-me/{scenario.lawsuit_id}/tasks",
        json={"task_type_id": scenario.task_type_id, "comments": "Favor juntar procuração"},
        headers=scenario.partner_headers,
    )
    assert response.status_code == 403


async def test_revogar_corta_o_acesso_na_hora(scenario: Scenario, client: AsyncClient) -> None:
    """Regra 6."""
    share_id = await _share(client, scenario)

    revoked = await client.delete(
        f"/api/v1/lawsuits/{scenario.lawsuit_id}/share/{share_id}",
        headers=scenario.owner_headers,
    )
    assert revoked.status_code == 204

    response = await client.get(
        "/api/v1/partnerships/shared-with-me", headers=scenario.partner_headers
    )
    assert response.json()["items"] == []
    detail = await client.get(
        f"/api/v1/partnerships/shared-with-me/{scenario.lawsuit_id}",
        headers=scenario.partner_headers,
    )
    assert detail.status_code == 404


async def test_revogar_preserva_o_que_o_parceiro_criou(
    scenario: Scenario, client: AsyncClient
) -> None:
    """Regra 6, segunda metade: corta o acesso, não o trabalho já feito."""
    share_id = await _share(client, scenario)
    created = await client.post(
        f"/api/v1/partnerships/shared-with-me/{scenario.lawsuit_id}/tasks",
        json={"task_type_id": scenario.task_type_id, "comments": "Audiência marcada"},
        headers=scenario.partner_headers,
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["post_id"]

    await client.delete(
        f"/api/v1/lawsuits/{scenario.lawsuit_id}/share/{share_id}",
        headers=scenario.owner_headers,
    )

    still_there = await client.get(f"/api/v1/posts/{post_id}", headers=scenario.owner_headers)
    assert still_there.status_code == 200
    assert still_there.json()["comments"] == "Audiência marcada"


async def test_encerrar_parceria_revoga_tudo_dos_dois_lados(
    scenario: Scenario, client: AsyncClient
) -> None:
    """Regra 7."""
    await _share(client, scenario)

    ended = await client.post(
        f"/api/v1/partnerships/{scenario.partnership_id}/end", headers=scenario.partner_headers
    )
    assert ended.status_code == 204

    shared = await client.get(
        "/api/v1/partnerships/shared-with-me", headers=scenario.partner_headers
    )
    assert shared.json()["items"] == []

    owner_shares = await client.get(
        f"/api/v1/lawsuits/{scenario.lawsuit_id}/shares", headers=scenario.owner_headers
    )
    assert owner_shares.json()["items"] == []

    for headers in (scenario.owner_headers, scenario.partner_headers):
        listing = await client.get("/api/v1/partnerships", headers=headers)
        assert listing.json()["items"][0]["status"] == "ENCERRADA"


async def test_tarefa_de_parceiro_aparece_nas_duas_caixas(
    scenario: Scenario, client: AsyncClient
) -> None:
    """Regra 8: a demanda do parceiro cai na caixa de entrada do dono (a tarefa nasce no
    tenant dele, marcada com a origem) e volta para o parceiro na lista do processo
    compartilhado — a caixa do parceiro é essa, ver §9 Descobertas."""
    await _share(client, scenario)

    created = await client.post(
        f"/api/v1/partnerships/shared-with-me/{scenario.lawsuit_id}/tasks",
        json={"task_type_id": scenario.task_type_id, "comments": "Protocolar recurso"},
        headers=scenario.partner_headers,
    )
    assert created.status_code == 201, created.text
    post_id = created.json()["post_id"]

    # A tarefa nasce não lida, então cai na seção "unread" da caixa do dono (spec 036).
    inbox = await client.get(
        "/api/v1/inbox", params={"section": "unread"}, headers=scenario.owner_headers
    )
    assert inbox.status_code == 200, inbox.text
    assert post_id in [item["post_id"] for item in inbox.json()["items"]]

    detail = await client.get(
        f"/api/v1/partnerships/shared-with-me/{scenario.lawsuit_id}",
        headers=scenario.partner_headers,
    )
    tasks = detail.json()["tasks"]
    assert [task["id"] for task in tasks] == [post_id]
    assert tasks[0]["from_partner"] is True

    # Regra 10: a demanda conta para os dois lados, cada um do seu ângulo.
    owner_summary = await client.get("/api/v1/partnerships/summary", headers=scenario.owner_headers)
    assert owner_summary.json()["pending_by_office"] == 1
    partner_summary = await client.get(
        "/api/v1/partnerships/summary", headers=scenario.partner_headers
    )
    assert partner_summary.json()["pending_by_partner"] == 1


async def test_parceiro_nao_acessa_bi_nem_relatorios_do_dono(
    scenario: Scenario, client: AsyncClient
) -> None:
    """VAZAMENTO (regra 4): o processo compartilhado não entra em nenhuma agregação do
    parceiro — é por isso que o acesso não passou por afrouxar RLS."""
    await _share(client, scenario, can_view_financial=True)

    report = await client.get(
        "/api/v1/reports/tabular/new_lawsuits", headers=scenario.partner_headers
    )
    assert report.status_code == 200
    assert report.json()["items"] == []

    stats = await client.get("/api/v1/lawsuits/stats", headers=scenario.partner_headers)
    assert stats.status_code == 200
    assert stats.json()["active"]["value"] == 0

    portfolio = await client.get("/api/v1/bi/pipeline/portfolio", headers=scenario.partner_headers)
    assert portfolio.status_code == 200
    assert all(row.get("lawsuits", 0) == 0 for row in portfolio.json().get("items", []))

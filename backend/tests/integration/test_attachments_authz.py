"""Spec 135, regra 3 — a autorização de anexo vale em TODO caminho que chega ao arquivo.

Um anexo tem duas guardas: a visibilidade da tarefa privada (spec 035, regra 7) e o eixo
financeiro, quando o alvo é um lançamento. Até esta spec as duas existiam só em alguns
caminhos: a rota genérica `/attachments` aceitava `attached_to_type="transaction"` sem
olhar `financial_access`, e a extração de documento buscava o anexo direto no repositório e
devolvia o CONTEÚDO do arquivo dentro do texto extraído.

Os testes abaixo entram pelos caminhos que NÃO passavam pela guarda, com o mesmo anexo que
o caminho legítimo protege — é a única forma de afirmar que a guarda é do anexo, e não da
rota.
"""

import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.users.models import FinancialAccess, UserRole
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_lawsuits import _auth_header
from tests.integration.test_lawsuits_listing import LawsuitFactory, _make_factory
from tests.integration.test_posts import _create_post, _create_task_type
from tests.integration.test_transactions import _fixtures, _make_gestor_full, _receita_payload

_PDF = ("comprovante.pdf", b"%PDF-1.4 conteudo", "application/pdf")


@pytest.fixture
async def factory(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> LawsuitFactory:
    return await _make_factory(client, make_user, app_session_factory)


async def _lancamento_com_anexo(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> tuple[SeededUser, str, str]:
    """Um lançamento com um comprovante, criados pelo caminho legítimo (FULL).

    Devolve `(gestor, transaction_id, attachment_id)` — o `attachment_id` é o UUID que os
    testes abaixo tentam usar por fora.
    """
    gestor, headers = await _make_gestor_full(make_user)
    receita_id, _despesa, cost_center_id, account_a, _b = await _fixtures(client, headers)
    criado = await client.post(
        "/api/v1/transactions",
        json=_receita_payload(
            category_id=receita_id, cost_center_id=cost_center_id, account_id=account_a
        ),
        headers=headers,
    )
    assert criado.status_code == 201, criado.text
    transaction_id = str(criado.json()["id"])

    upload = await client.post(
        f"/api/v1/transactions/{transaction_id}/attachments",
        files={"file": _PDF},
        headers=headers,
    )
    assert upload.status_code == 201, upload.text
    return gestor, transaction_id, str(upload.json()["id"])


async def test_sem_acesso_financeiro_a_rota_generica_nao_lista_anexo_de_lancamento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """O comentário do service dizia "quem chega aqui já passou por `require_financial`".
    A premissa valia para `/transactions/{id}/attachments` e não para esta rota."""
    gestor, transaction_id, _anexo = await _lancamento_com_anexo(client, make_user)
    sem_acesso = await make_user(
        tenant_id=gestor.tenant_id, role=UserRole.GESTOR, financial_access=FinancialAccess.NONE
    )

    resposta = await client.get(
        "/api/v1/attachments",
        params={"attached_to_type": "transaction", "attached_to_id": transaction_id},
        headers=auth_header(sem_acesso),
    )

    # 404, não 403: responder "proibido" confirmaria que o lançamento existe.
    assert resposta.status_code == 404


async def test_sem_acesso_financeiro_nao_baixa_anexo_de_lancamento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    gestor, _transaction_id, anexo_id = await _lancamento_com_anexo(client, make_user)
    sem_acesso = await make_user(
        tenant_id=gestor.tenant_id, role=UserRole.GESTOR, financial_access=FinancialAccess.NONE
    )

    resposta = await client.get(
        f"/api/v1/attachments/{anexo_id}/download", headers=auth_header(sem_acesso)
    )

    assert resposta.status_code == 404


async def test_leitura_financeira_baixa_o_anexo_do_lancamento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """A guarda é o gate, não um bug que fecha para todo mundo."""
    gestor, transaction_id, anexo_id = await _lancamento_com_anexo(client, make_user)
    leitor = await make_user(
        tenant_id=gestor.tenant_id,
        role=UserRole.COLABORADOR,
        financial_access=FinancialAccess.READ_ONLY,
    )
    headers = auth_header(leitor)

    listagem = await client.get(
        "/api/v1/attachments",
        params={"attached_to_type": "transaction", "attached_to_id": transaction_id},
        headers=headers,
    )
    download = await client.get(f"/api/v1/attachments/{anexo_id}/download", headers=headers)

    assert listagem.status_code == 200
    assert [item["id"] for item in listagem.json()] == [anexo_id]
    assert download.status_code == 200


async def test_leitura_financeira_nao_sobe_anexo_em_lancamento(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Subir comprovante é escrita no financeiro: READ_ONLY lê e não escreve, aqui como
    em `/transactions/{id}/attachments` (que exige FULL desde a spec 058)."""
    gestor, transaction_id, _anexo = await _lancamento_com_anexo(client, make_user)
    leitor = await make_user(
        tenant_id=gestor.tenant_id,
        role=UserRole.COLABORADOR,
        financial_access=FinancialAccess.READ_ONLY,
    )

    resposta = await client.post(
        "/api/v1/attachments",
        data={"attached_to_type": "transaction", "attached_to_id": transaction_id},
        files={"file": ("nota.pdf", b"%PDF-1.4 x", "application/pdf")},
        headers=auth_header(leitor),
    )

    assert resposta.status_code == 404


async def test_extracao_nao_le_anexo_de_lancamento_sem_acesso_financeiro(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """`POST /documents/extract?attachment_id=` devolve o conteúdo do arquivo dentro do
    texto extraído — era o caminho de leitura de anexo mais barato do sistema, e o único
    que não passava por `AttachmentService`."""
    gestor, _transaction_id, anexo_id = await _lancamento_com_anexo(client, make_user)
    sem_acesso = await make_user(
        tenant_id=gestor.tenant_id, role=UserRole.COLABORADOR, financial_access=FinancialAccess.NONE
    )

    resposta = await client.post(
        "/api/v1/documents/extract",
        data={"attachment_id": anexo_id},
        headers=auth_header(sem_acesso),
    )

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Anexo não encontrado."


async def test_extracao_nao_le_anexo_de_tarefa_privada_de_outro(
    client: AsyncClient,
    factory: LawsuitFactory,
    make_user: Callable[..., Awaitable[SeededUser]],
) -> None:
    """Regra 7 da spec 035 no caminho da extração: a tarefa privada não é vista nem pelo
    GESTOR, e o anexo dela segue a tarefa."""
    lawsuit_id = await factory.create()
    task_type_id = await _create_task_type(client, factory.headers)
    dono = await make_user(tenant_id=factory.gestor.tenant_id, role=UserRole.COLABORADOR)
    headers_dono = _auth_header(dono)

    privada = await _create_post(
        client,
        headers_dono,
        lawsuit_id=lawsuit_id,
        task_type_id=task_type_id,
        user_ids=[str(dono.user_id)],
        is_private=True,
    )
    upload = await client.post(
        "/api/v1/attachments",
        data={"attached_to_type": "post", "attached_to_id": privada["id"]},
        files={"file": _PDF},
        headers=headers_dono,
    )
    assert upload.status_code == 201, upload.text

    # O GESTOR do escritório — que não vê a tarefa — tentando ler o anexo pela extração.
    resposta = await client.post(
        "/api/v1/documents/extract",
        data={"attachment_id": upload.json()["id"]},
        headers=factory.headers,
    )

    assert resposta.status_code == 404


async def test_extracao_de_anexo_inexistente_continua_404(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """A mesma resposta do anexo negado — quem não pode ver não distingue os dois casos,
    e é isso que impede a rota de virar um oráculo de existência."""
    seeded = await make_user(role=UserRole.COLABORADOR)

    resposta = await client.post(
        "/api/v1/documents/extract",
        data={"attachment_id": str(uuid.uuid4())},
        headers=auth_header(seeded),
    )

    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "Anexo não encontrado."

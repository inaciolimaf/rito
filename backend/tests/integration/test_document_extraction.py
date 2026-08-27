"""Extração de documentos (spec 091 §8).

Nenhum OCR e nenhum LLM de verdade rodam aqui: os dois entram por Protocol (CLAUDE.md
§5), e o teste passa uma implementação própria — que é o que o LSP permite. O
armazenamento, esse é real (MinIO), porque a spec exige LER o arquivo de volta e um fake
de storage esconderia justamente o que pode quebrar.
"""

import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.rls import set_tenant_context
from app.domain.ai.models import AiAction, AiAuditLog
from app.domain.customers.models import Customer
from app.domain.documents.models import Document, DocumentExtraction
from app.domain.users.models import UserRole
from app.integrations.ocr.base import OcrError, OcrResult
from app.integrations.openrouter.types import LLMResponse, Usage
from tests.integration.conftest import SeededUser, auth_header
from tests.integration.test_ai_copilot import ScriptedProvider
from tests.integration.test_lawsuits import _auth_header

pytestmark = pytest.mark.asyncio

# CPF válido de teste (fecha o dígito verificador) e um que NÃO fecha — a diferença entre
# os dois é o que a regra 4 trata.
CPF_VALIDO = "11144477735"
CPF_INVALIDO = "11144477700"

RG_TEXTO = "REPÚBLICA FEDERATIVA DO BRASIL\nCARTEIRA DE IDENTIDADE\nAna Paula Ribeiro"


class FakeOcr:
    """Implementação de `OcrProvider` (LSP): devolve o texto que o teste mandou."""

    def __init__(
        self, *, text: str = RG_TEXTO, page_count: int = 1, error: str | None = None
    ) -> None:
        self.text = text
        self.page_count = page_count
        self.error = error
        self.calls = 0

    @property
    def is_available(self) -> bool:
        return self.error is None

    async def extract_text(self, *, content: bytes, content_type: str) -> OcrResult:
        self.calls += 1
        if self.error is not None:
            raise OcrError(self.error)
        return OcrResult(text=self.text, page_count=self.page_count)


def _leitura(fields: dict[str, Any], *, kind: str = "rg", target: str = "customer") -> LLMResponse:
    return LLMResponse(
        content=json.dumps(
            {"document_kind": kind, "target_type": target, "fields": fields}, ensure_ascii=False
        ),
        usage=Usage(prompt_tokens=300, completion_tokens=80),
        model="fabricante-x/modelo-y",
        finish_reason="stop",
    )


_RG_FIELDS = {
    "name": {"value": "Ana Paula Ribeiro", "confidence": 0.97},
    "identification": {"value": CPF_VALIDO, "confidence": 0.93},
    "birth_date": {"value": "1988-03-14", "confidence": 0.9},
}


def _use(*, llm: object | None = None, ocr: object | None = None) -> None:
    from app.core.deps import get_ocr_provider
    from app.domain.ai.router import get_llm_provider
    from app.main import app

    if llm is not None:
        app.dependency_overrides[get_llm_provider] = lambda: llm
    if ocr is not None:
        app.dependency_overrides[get_ocr_provider] = lambda: ocr


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    from app.core.deps import get_ocr_provider
    from app.domain.ai.router import get_llm_provider
    from app.main import app

    yield
    app.dependency_overrides.pop(get_llm_provider, None)
    app.dependency_overrides.pop(get_ocr_provider, None)


def _pdf_com_texto(texto: str, *, pages: int = 1) -> bytes:
    """PDF de verdade, com texto de verdade — o `pypdf` precisa achar alguma coisa lá
    dentro para a regra 1 significar algo."""
    from fpdf import FPDF

    pdf = FPDF()
    for _ in range(pages):
        pdf.add_page()
        pdf.set_font("helvetica", size=12)
        pdf.multi_cell(0, 8, texto)
    return bytes(pdf.output())


async def _extract(
    client: AsyncClient,
    user: SeededUser,
    *,
    content: bytes,
    filename: str = "documento.pdf",
    content_type: str = "application/pdf",
    expected_kind: str | None = None,
) -> Any:
    data = {"expected_kind": expected_kind} if expected_kind else {}
    return await client.post(
        "/api/v1/documents/extract",
        files={"file": (filename, content, content_type)},
        data=data,
        headers=auth_header(user),
    )


async def _origin(client: AsyncClient, user: SeededUser) -> str:
    from tests.integration.test_customers import _create_origin

    return await _create_origin(client, _auth_header(user), f"Origem {uuid.uuid4().hex[:6]}")


# ----------------------------------------------------------------- leitura do texto


async def test_pdf_com_texto_pula_o_ocr(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 1: rasterizar e reconhecer o que já está escrito é gastar para piorar."""
    user = await make_user(role=UserRole.GESTOR)
    ocr = FakeOcr()
    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=ocr)

    resposta = await _extract(client, user, content=_pdf_com_texto(RG_TEXTO))

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["used_ocr"] is False
    assert ocr.calls == 0


async def test_imagem_passa_pelo_ocr(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    ocr = FakeOcr()
    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=ocr)

    resposta = await _extract(
        client,
        user,
        content=b"\x89PNG\r\n\x1a\n" + b"0" * 200,
        filename="rg.png",
        content_type="image/png",
    )

    assert resposta.status_code == 201, resposta.text
    assert resposta.json()["used_ocr"] is True
    assert ocr.calls == 1
    assert RG_TEXTO in resposta.json()["ocr_text"]


# --------------------------------------------------------------------- extração


async def test_extracao_de_rg_preenche_os_campos(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=FakeOcr())

    corpo = (await _extract(client, user, content=_pdf_com_texto(RG_TEXTO))).json()

    assert corpo["document_kind"] == "rg"
    assert corpo["target_type"] == "customer"
    assert corpo["fields"]["name"]["value"] == "Ana Paula Ribeiro"
    assert corpo["fields"]["identification"]["prefill"] is True


async def test_extracao_de_contrato_social_preenche_pj(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 2: o tipo informado pelo usuário manda — ele está com o papel na mão."""
    user = await make_user(role=UserRole.GESTOR)
    campos = {
        "name": {"value": "Ribeiro Alimentos LTDA", "confidence": 0.95},
        "identification": {"value": "11222333000181", "confidence": 0.92},
        "city": {"value": "Fortaleza", "confidence": 0.88},
    }
    _use(
        llm=ScriptedProvider(script=[_leitura(campos, kind="peticao")]),
        ocr=FakeOcr(),
    )

    corpo = (
        await _extract(
            client,
            user,
            content=_pdf_com_texto("CONTRATO SOCIAL"),
            expected_kind="contrato_social",
        )
    ).json()

    assert corpo["document_kind"] == "contrato_social"
    assert corpo["fields"]["identification"]["is_valid"] is True


async def test_confianca_baixa_nao_pre_preenche(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 3: abaixo de 0,7 deixa de ser mais rápido conferir do que digitar."""
    user = await make_user(role=UserRole.GESTOR)
    campos = {
        "name": {"value": "Ana Paula Ribeiro", "confidence": 0.97},
        "birth_date": {"value": "1988-03-14", "confidence": 0.55},
    }
    _use(llm=ScriptedProvider(script=[_leitura(campos)]), ocr=FakeOcr())

    corpo = (await _extract(client, user, content=_pdf_com_texto(RG_TEXTO))).json()

    assert corpo["fields"]["name"]["prefill"] is True
    assert corpo["fields"]["birth_date"]["prefill"] is False
    # O valor continua na resposta: a tela mostra destacado, não escondido.
    assert corpo["fields"]["birth_date"]["value"] == "1988-03-14"


async def test_cpf_invalido_e_marcado_nao_descartado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 4: quase sempre é erro de OCR num documento legítimo. Descartar obrigaria a
    digitar tudo de novo — exatamente o que a feature existe para evitar."""
    user = await make_user(role=UserRole.GESTOR)
    campos = {
        "name": {"value": "Ana Paula Ribeiro", "confidence": 0.97},
        "identification": {"value": CPF_INVALIDO, "confidence": 0.8},
    }
    _use(llm=ScriptedProvider(script=[_leitura(campos)]), ocr=FakeOcr())

    corpo = (await _extract(client, user, content=_pdf_com_texto(RG_TEXTO))).json()

    assert corpo["fields"]["identification"]["value"] == CPF_INVALIDO
    assert corpo["fields"]["identification"]["is_valid"] is False


# ---------------------------------------------------------------------- aplicar


async def test_aplicar_passa_por_ai_actions(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 5, o teste central: o cadastro nasce pelo mesmo caminho auditado de
    qualquer escrita de IA — com preview, execução pelo service do domínio e registro."""
    user = await make_user(role=UserRole.GESTOR)
    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=FakeOcr())
    extraction_id = (await _extract(client, user, content=_pdf_com_texto(RG_TEXTO))).json()["id"]
    origin_id = await _origin(client, user)

    aplicada = await client.post(
        f"/api/v1/documents/extractions/{extraction_id}/apply",
        json={
            "target_type": "customer",
            "arguments": {
                "name": "Ana Paula Ribeiro",
                "origin_id": origin_id,
                "type": "PF",
                "identification": CPF_VALIDO,
            },
            "corrections": {},
        },
        headers=auth_header(user),
    )

    assert aplicada.status_code == 200, aplicada.text
    assert aplicada.json()["status"] == "applied"

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        acoes = list((await session.scalars(select(AiAction))).all())
        auditoria = list((await session.scalars(select(AiAuditLog))).all())
        clientes = list((await session.scalars(select(Customer))).all())

    assert [acao.tool_name for acao in acoes] == ["create_customer"]
    assert acoes[0].status == "executed"
    assert len(auditoria) == 1, "o que a IA gravou tem de estar na auditoria"
    assert [cliente.name for cliente in clientes] == ["Ana Paula Ribeiro"]


async def test_correcao_humana_e_gravada(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 6: é o único jeito de saber se a extração está piorando."""
    user = await make_user(role=UserRole.GESTOR)
    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=FakeOcr())
    extraction_id = (await _extract(client, user, content=_pdf_com_texto(RG_TEXTO))).json()["id"]
    origin_id = await _origin(client, user)

    await client.post(
        f"/api/v1/documents/extractions/{extraction_id}/apply",
        json={
            "target_type": "customer",
            "arguments": {
                "name": "Ana Paula Ribeiro Silva",
                "origin_id": origin_id,
                "type": "PF",
                "identification": CPF_VALIDO,
            },
            "corrections": {"name": "Ana Paula Ribeiro Silva"},
        },
        headers=auth_header(user),
    )

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        extraction = (await session.scalars(select(DocumentExtraction))).one()

    assert extraction.corrections["name"] == {
        "extracted": "Ana Paula Ribeiro",
        "corrected": "Ana Paula Ribeiro Silva",
    }


async def test_arquivo_vinculado_ao_registro_criado(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[SeededUser]],
    app_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Regra 7: a primeira pergunta ao conferir um cadastro é 'de onde veio isso?'."""
    user = await make_user(role=UserRole.GESTOR)
    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=FakeOcr())
    extraction_id = (
        await _extract(client, user, content=_pdf_com_texto(RG_TEXTO), filename="rg-ana.pdf")
    ).json()["id"]
    origin_id = await _origin(client, user)

    aplicada = await client.post(
        f"/api/v1/documents/extractions/{extraction_id}/apply",
        json={
            "target_type": "customer",
            "arguments": {
                "name": "Ana Paula Ribeiro",
                "origin_id": origin_id,
                "type": "PF",
                "identification": CPF_VALIDO,
            },
        },
        headers=auth_header(user),
    )
    customer_id = uuid.UUID(aplicada.json()["applied_id"])

    async with app_session_factory() as session, session.begin():
        await set_tenant_context(session, user.tenant_id)
        documentos = list((await session.scalars(select(Document))).all())

    assert [documento.filename for documento in documentos] == ["rg-ana.pdf"]
    assert documentos[0].scope_id == customer_id
    assert documentos[0].scope_type.value == "CUSTOMER"


async def test_duplicata_oferece_atualizar(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 8: duplicata de contato é das piores sujeiras de um escritório — o processo
    fica pendurado num cadastro e o financeiro no outro."""
    user = await make_user(role=UserRole.GESTOR)
    origin_id = await _origin(client, user)
    criado = await client.post(
        "/api/v1/customers",
        json={
            "name": "Ana Paula Ribeiro",
            "type": "PF",
            "origin_id": origin_id,
            "identification": CPF_VALIDO,
        },
        headers=auth_header(user),
    )
    assert criado.status_code == 201, criado.text
    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=FakeOcr())

    corpo = (await _extract(client, user, content=_pdf_com_texto(RG_TEXTO))).json()

    assert corpo["duplicate"] is not None
    assert corpo["duplicate"]["customer_id"] == criado.json()["id"]


# ------------------------------------------------------------------- limites


async def test_acima_de_vinte_paginas_e_recusado(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 9: o limite de páginas protege a conta de tokens, não a memória."""
    user = await make_user(role=UserRole.GESTOR)
    provider = ScriptedProvider(script=[_leitura(_RG_FIELDS)])
    _use(llm=provider, ocr=FakeOcr())

    resposta = await _extract(client, user, content=_pdf_com_texto("PETIÇÃO", pages=21))

    assert resposta.status_code == 422
    assert "21 páginas" in resposta.json()["detail"]
    assert provider.prompts == [], "nem chegou a chamar o modelo"


async def test_ilegivel_devolve_erro_com_o_texto_lido(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 10: é com o texto lido que a pessoa descobre se o problema foi a foto torta
    ou o documento errado."""
    user = await make_user(role=UserRole.GESTOR)
    _use(llm=ScriptedProvider(script=[_leitura({})]), ocr=FakeOcr(text="rgb  \n |||"))

    resposta = await _extract(
        client,
        user,
        content=b"\x89PNG\r\n\x1a\n" + b"0" * 50,
        filename="borrado.png",
        content_type="image/png",
    )

    assert resposta.status_code == 422
    corpo = resposta.json()
    assert "nenhum campo reconhecível" in corpo["detail"]
    assert corpo["ocr_text"] == "rgb  \n |||"


async def test_sem_ocr_no_servidor_a_mensagem_explica(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    """Regra 12, na versão que importa aqui: sem motor de OCR o sistema continua de pé e
    diz o que falta, em vez de estourar um erro de subprocesso."""
    user = await make_user(role=UserRole.GESTOR)
    from app.integrations.ocr.tesseract import UnavailableOcr

    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=UnavailableOcr())

    resposta = await _extract(
        client, user, content=b"\x89PNG" + b"0" * 40, filename="rg.png", content_type="image/png"
    )

    assert resposta.status_code == 422
    assert "OCR" in resposta.json()["detail"]


async def test_descartar_encerra_a_extracao(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    user = await make_user(role=UserRole.GESTOR)
    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=FakeOcr())
    extraction_id = (await _extract(client, user, content=_pdf_com_texto(RG_TEXTO))).json()["id"]

    descartada = await client.post(
        f"/api/v1/documents/extractions/{extraction_id}/discard", headers=auth_header(user)
    )

    assert descartada.status_code == 200
    assert descartada.json()["status"] == "discarded"


async def test_extracao_de_outro_escritorio_nao_existe(
    client: AsyncClient, make_user: Callable[..., Awaitable[SeededUser]]
) -> None:
    dono = await make_user(role=UserRole.GESTOR)
    intruso = await make_user(role=UserRole.GESTOR)
    _use(llm=ScriptedProvider(script=[_leitura(_RG_FIELDS)]), ocr=FakeOcr())
    extraction_id = (await _extract(client, dono, content=_pdf_com_texto(RG_TEXTO))).json()["id"]

    resposta = await client.get(
        f"/api/v1/documents/extractions/{extraction_id}", headers=auth_header(intruso)
    )

    assert resposta.status_code == 404

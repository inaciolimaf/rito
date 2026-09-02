"""Extração de campos a partir de um documento (spec 091).

O caminho é sempre o mesmo: **texto → modelo → revisão humana → cadastro**. O que muda é
de onde vem o texto — PDF com texto embutido não passa pelo OCR (regra 1), porque
rasterizar e reconhecer o que já está escrito é gastar processamento para piorar o
resultado.

Nada aqui grava cadastro. A gravação acontece pelo fluxo de `ai_actions` (084), que é o
mesmo por onde passa qualquer escrita proposta por IA: preview, confirmação, auditoria.
"""

import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.prompts import load_prompt
from app.ai.tools.base import ToolContext
from app.ai.tools.write import get_write_tool
from app.core.br_documents import (
    is_valid_cpf_or_cnpj,
    is_valid_postal_code,
    strip_document_mask,
)
from app.core.repository import BaseRepository
from app.domain.ai.actions import AiActionService
from app.domain.ai.service import AiRunner
from app.domain.customers.repository import CustomerRepository
from app.domain.documents.models import (
    Document,
    DocumentExtraction,
    DocumentScopeType,
    ExtractionStatus,
)
from app.domain.users.models import User
from app.integrations.ocr.base import OcrError, OcrProvider
from app.integrations.openrouter.types import Message
from app.integrations.storage.base import FileStorage

FEATURE_KEY = "document_extraction"

# Regra 9. Os dois limites existem por motivos diferentes: o tamanho protege a memória do
# processo, o número de páginas protege a conta de tokens.
MAX_SIZE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 20

# Regra 3: abaixo disso o campo aparece destacado e NÃO entra pré-preenchido. O número
# não é mágico — é onde deixa de ser mais rápido conferir do que digitar.
MIN_CONFIDENCE = 0.7

# Abaixo disso, o "texto embutido" do PDF é ruído de layout (numeração de página, marca
# d'água) e vale a pena tentar o OCR (regra 1, na direção inversa).
MIN_EMBEDDED_TEXT_CHARS = 40

# Campos em que um valor mal lido é caro, e que têm validador desde a spec 018.
_DOCUMENT_FIELDS = frozenset({"identification", "rep_identification"})
_POSTAL_FIELDS = frozenset({"postal_code"})

_KNOWN_KINDS = frozenset({"rg", "cnh", "contrato_social", "procuracao", "peticao"})
_SYSTEM_PROMPT = load_prompt("document_extraction")


class ExtractionTooLargeError(Exception):
    """Regra 9: acima de 20 MB ou 20 páginas → 422 pedindo recorte."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class UnreadableDocumentError(Exception):
    """Regra 10: ilegível devolve erro claro — e o texto lido junto, para conferência."""

    def __init__(self, detail: str, *, ocr_text: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.ocr_text = ocr_text


class ExtractionNotPendingError(Exception):
    """Extração já aplicada ou descartada não volta atrás."""


@dataclass(frozen=True)
class ExtractedText:
    text: str
    page_count: int
    used_ocr: bool


def read_pdf_text(content: bytes) -> ExtractedText:
    """Texto embutido do PDF, sem OCR (regra 1).

    `pypdf` é importado aqui dentro porque a maioria das requests do sistema não tem nada
    a ver com PDF, e o import custa.
    """
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io_bytes(content))
        paginas = [(page.extract_text() or "") for page in reader.pages]
    except (PdfReadError, OSError, ValueError) as exc:
        raise UnreadableDocumentError(f"O PDF não pôde ser aberto: {exc}") from exc
    return ExtractedText(text="\n".join(paginas).strip(), page_count=len(paginas), used_ocr=False)


def io_bytes(content: bytes) -> Any:
    import io

    return io.BytesIO(content)


def parse_extraction(raw: str | None) -> dict[str, Any]:
    """Saída do modelo → dicionário. JSON quebrado vira erro de leitura, não 500."""
    if not raw:
        raise UnreadableDocumentError("O modelo não devolveu nada sobre este documento.")
    texto = raw.strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-z]*\n|\n```$", "", texto).strip()
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as exc:
        raise UnreadableDocumentError(
            "Não foi possível entender o documento — a leitura veio ilegível."
        ) from exc
    if not isinstance(dados, dict):
        raise UnreadableDocumentError("A leitura do documento veio num formato inesperado.")
    return dados


def normalize_fields(raw_fields: Any) -> dict[str, dict[str, Any]]:
    """Cada campo vira `{value, confidence, prefill, is_valid}`.

    `prefill` é decisão do servidor, não da tela (regra 3): duas telas diferentes lendo a
    mesma confiança e decidindo diferente seria a pior forma de inconsistência.
    """
    if not isinstance(raw_fields, dict):
        return {}
    campos: dict[str, dict[str, Any]] = {}
    for nome, bruto in raw_fields.items():
        if isinstance(bruto, dict):
            valor = bruto.get("value")
            confianca = bruto.get("confidence")
        else:
            valor, confianca = bruto, None
        if valor is None or str(valor).strip() == "":
            continue
        valor = str(valor).strip()
        try:
            confianca = round(float(confianca), 2) if confianca is not None else 0.0
        except (TypeError, ValueError):
            confianca = 0.0
        confianca = min(max(confianca, 0.0), 1.0)
        campos[str(nome)] = {
            "value": valor,
            "confidence": confianca,
            "prefill": confianca >= MIN_CONFIDENCE,
            **_validity(str(nome), valor),
        }
    return campos


def _validity(nome: str, valor: str) -> dict[str, Any]:
    """Regra 4: inválido é MARCADO, nunca descartado.

    Um CPF que não fecha o dígito verificador quase sempre é erro de OCR num documento
    legítimo — jogar o campo fora obrigaria a pessoa a digitar tudo de novo, que é
    exatamente o que esta feature existe para evitar.
    """
    if nome in _DOCUMENT_FIELDS:
        digitos = strip_document_mask(valor)
        return {"is_valid": is_valid_cpf_or_cnpj(digitos), "value_digits": digitos}
    if nome in _POSTAL_FIELDS:
        return {"is_valid": is_valid_postal_code(valor)}
    return {"is_valid": True}


def _recusar_se_longo(paginas: int) -> None:
    """Teto de páginas, cobrado tanto no texto embutido quanto no resultado do OCR."""
    if paginas > MAX_PAGES:
        raise ExtractionTooLargeError(
            f"O documento tem {paginas} páginas e o limite é {MAX_PAGES}. "
            "Envie um recorte com as páginas que interessam."
        )


def _texto_embutido(content: bytes, content_type: str) -> ExtractedText | None:
    """Regra 1: OCR só quando NÃO há texto para ler.

    PDF gerado por editor já traz o texto; passar isso por OCR seria pagar segundos de
    processamento para reconhecer o que já estava escrito. `None` significa «não deu, siga
    para o OCR» — um PDF escaneado tem página, mas quase nenhum caractere.
    """
    if content_type != "application/pdf":
        return None
    embutido = read_pdf_text(content)
    _recusar_se_longo(embutido.page_count)
    return embutido if len(embutido.text) >= MIN_EMBEDDED_TEXT_CHARS else None


class DocumentExtractionRepository(BaseRepository[DocumentExtraction]):
    model = DocumentExtraction

    async def pending(self, limit: int) -> list[DocumentExtraction]:
        stmt = (
            select(DocumentExtraction)
            .where(DocumentExtraction.status == ExtractionStatus.PENDING.value)
            .order_by(DocumentExtraction.created_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())


class DocumentExtractionService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        storage: FileStorage,
        runner: AiRunner,
        ocr: OcrProvider,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.storage = storage
        self.runner = runner
        self.ocr = ocr
        self.extractions = DocumentExtractionRepository(session)
        self.customers = CustomerRepository(session)
        self.actions = AiActionService(session, tenant_id)

    # ------------------------------------------------------------------ ler

    async def read_text(self, *, content: bytes, content_type: str) -> ExtractedText:
        """Regra 1: OCR só quando não há texto para ler."""
        if len(content) > MAX_SIZE_BYTES:
            raise ExtractionTooLargeError(
                f"O arquivo tem {len(content) // (1024 * 1024)} MB e o limite é 20 MB. "
                "Envie um recorte com as páginas que interessam."
            )
        embutido = _texto_embutido(content, content_type)
        if embutido is not None:
            return embutido
        try:
            resultado = await self.ocr.extract_text(content=content, content_type=content_type)
        except OcrError as exc:
            raise UnreadableDocumentError(str(exc)) from exc
        _recusar_se_longo(resultado.page_count)
        if not resultado.text.strip():
            raise UnreadableDocumentError(
                "Não foi possível ler nada neste documento. Confira se a imagem está "
                "nítida e na posição correta.",
                ocr_text="",
            )
        return ExtractedText(text=resultado.text, page_count=resultado.page_count, used_ocr=True)

    # -------------------------------------------------------------- extrair

    async def extract(
        self,
        *,
        user: User,
        content: bytes,
        filename: str,
        content_type: str,
        storage_key: str,
        attachment_id: uuid.UUID | None = None,
        expected_kind: str | None = None,
    ) -> DocumentExtraction:
        lido = await self.read_text(content=content, content_type=content_type)
        resposta = await self.runner.run(
            feature_key=FEATURE_KEY,
            messages=[
                Message(role="system", content=_SYSTEM_PROMPT),
                Message(role="user", content=_prompt_for(lido.text, expected_kind)),
            ],
            user_id=user.id,
            # Regra 11 (a razão real do cache): o mesmo arquivo reenviado depois de um
            # erro de rede não pode ser cobrado duas vezes.
            use_cache=True,
        )
        dados = parse_extraction(resposta.content)
        campos = normalize_fields(dados.get("fields"))
        if not campos:
            raise UnreadableDocumentError(
                "O documento foi lido, mas nenhum campo reconhecível foi encontrado nele.",
                ocr_text=lido.text,
            )

        extraction = DocumentExtraction(
            tenant_id=self.tenant_id,
            attachment_id=attachment_id,
            storage_key=storage_key,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            page_count=lido.page_count,
            user_id=user.id,
            document_kind=_kind_of(dados.get("document_kind"), expected_kind),
            ocr_text=lido.text,
            used_ocr=lido.used_ocr,
            extracted=campos,
            target_type=_target_of(dados.get("target_type")),
            model=resposta.model,
            tokens_used=resposta.usage.completion_tokens + resposta.usage.prompt_tokens,
        )
        self.session.add(extraction)
        await self.session.flush()
        return extraction

    async def duplicate_of(self, extraction: DocumentExtraction) -> Any:
        """Regra 8: CPF já cadastrado vira oferta de ATUALIZAR, não um segundo cadastro.

        Duplicata de contato é das piores sujeiras que um escritório acumula: o processo
        fica pendurado num cadastro e o financeiro no outro.
        """
        campo = (extraction.extracted or {}).get("identification")
        if not isinstance(campo, dict):
            return None
        digitos = str(campo.get("value_digits") or strip_document_mask(str(campo["value"])))
        if not digitos:
            return None
        return await self.customers.get_by_identification(digitos)

    # -------------------------------------------------------------- aplicar

    async def apply(
        self,
        extraction: DocumentExtraction,
        *,
        user: User,
        target_type: str,
        corrections: dict[str, Any],
        arguments: dict[str, Any],
    ) -> Any:
        """Regra 5: a gravação passa por `ai_actions` — preview, execução, auditoria.

        A confirmação humana da regra 4 do CLAUDE.md §7 é ESTA chamada: a tela de revisão
        já mostrou campo a campo, com confiança e validação, e a pessoa corrigiu o que
        quis. Pedir um segundo "confirma?" sobre o mesmo conteúdo não acrescentaria
        informação nenhuma — só treinaria a pessoa a clicar sem ler.
        """
        if extraction.status not in (
            ExtractionStatus.PENDING.value,
            ExtractionStatus.REVIEWED.value,
        ):
            raise ExtractionNotPendingError
        ferramenta = _TOOL_BY_TARGET.get(target_type)
        if ferramenta is None:
            raise ValueError(f"Alvo desconhecido: {target_type}")
        definition = get_write_tool(ferramenta)
        if definition is None:  # pragma: no cover - registro é estático
            raise ValueError(f"Ferramenta ausente: {ferramenta}")

        ctx = ToolContext(session=self.session, tenant_id=self.tenant_id, user=user)
        action = await self.actions.propose(
            ctx=ctx,
            definition=definition,
            arguments=arguments,
            model=extraction.model or "desconhecido",
        )
        extraction.target_type = target_type
        # Regra 6: o que o humano mudou fica gravado — é a métrica de qualidade da
        # extração, e o único jeito de saber se o modelo está piorando.
        extraction.corrections = _diff_corrections(extraction.extracted or {}, corrections)
        extraction.action_id = action.id
        extraction.status = ExtractionStatus.REVIEWED.value
        await self.session.flush()

        aprovada = await self.actions.approve(
            action, user=user, model=extraction.model or "desconhecido"
        )
        if aprovada.affected_id is not None:
            extraction.applied_id = aprovada.affected_id
            extraction.status = ExtractionStatus.APPLIED.value
            await self._file_document(extraction, user=user, affected_id=aprovada.affected_id)
        await self.session.flush()
        return aprovada

    async def discard(self, extraction: DocumentExtraction) -> DocumentExtraction:
        if extraction.status == ExtractionStatus.APPLIED.value:
            raise ExtractionNotPendingError
        extraction.status = ExtractionStatus.DISCARDED.value
        await self.session.flush()
        return extraction

    async def _file_document(
        self, extraction: DocumentExtraction, *, user: User, affected_id: uuid.UUID
    ) -> None:
        """Regra 7: o arquivo vai para a nuvem do registro que ele acabou de criar.

        Sem isto, o documento que originou o cadastro ficaria solto — e a primeira coisa
        que alguém pede ao conferir um cadastro é "de onde veio isso?".
        """
        escopo = (
            DocumentScopeType.CUSTOMER
            if extraction.target_type in ("customer", "customer_update")
            else DocumentScopeType.LAWSUIT
        )
        self.session.add(
            Document(
                tenant_id=self.tenant_id,
                scope_type=escopo,
                scope_id=affected_id,
                folder_id=None,
                storage_key=extraction.storage_key,
                filename=extraction.filename,
                content_type=extraction.content_type,
                size_bytes=extraction.size_bytes,
                uploaded_by=user.id,
            )
        )
        await self.session.flush()


_TOOL_BY_TARGET = {
    "customer": "create_customer",
    "customer_update": "update_customer",
    "lawsuit": "create_lawsuit",
}


def _diff_corrections(
    extraido: dict[str, Any], confirmado: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    correcoes: dict[str, dict[str, Any]] = {}
    for campo, valor in confirmado.items():
        original = extraido.get(campo)
        anterior = original.get("value") if isinstance(original, dict) else None
        if str(valor) != str(anterior if anterior is not None else ""):
            correcoes[campo] = {"extracted": anterior, "corrected": valor}
    return correcoes


def _kind_of(bruto: Any, expected: str | None) -> str | None:
    """Regra 2: `expected_kind` restringe. Quando o usuário disse que é um RG e o modelo
    achou outra coisa, quem manda é o usuário — ele está com o papel na mão."""
    if expected in _KNOWN_KINDS:
        return expected
    valor = str(bruto or "").strip().lower()
    return valor if valor in _KNOWN_KINDS else None


def _target_of(bruto: Any) -> str | None:
    valor = str(bruto or "").strip().lower()
    return valor if valor in ("customer", "lawsuit") else None


def _prompt_for(texto: str, expected_kind: str | None) -> str:
    cabecalho = "TEXTO LIDO DO DOCUMENTO:\n"
    if expected_kind in _KNOWN_KINDS:
        cabecalho = (
            f"O usuário informou que este documento é do tipo `{expected_kind}` — "
            "extraia os campos desse tipo.\n\n" + cabecalho
        )
    return cabecalho + texto

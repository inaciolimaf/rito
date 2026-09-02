"""Rotas de extração de documentos (spec 091 §5).

O arquivo entra por aqui de duas formas, e as duas existem por razões reais: um anexo que
já está no sistema (`attachment_id`) ou um upload direto — porque cadastrar um cliente a
partir do RG acontece antes de existir a ficha à qual anexar o arquivo.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_file_storage, get_ocr_provider
from app.core.permissions import UserRole, require_role
from app.domain.ai.exceptions import FeatureDisabledError
from app.domain.ai.router import get_llm_provider
from app.domain.ai.service import AiRunner
from app.domain.attachments.repository import AttachmentRepository
from app.domain.auth.deps import get_session_for_current_user
from app.domain.documents.extraction import (
    DocumentExtractionService,
    ExtractionNotPendingError,
    ExtractionTooLargeError,
    UnreadableDocumentError,
)
from app.domain.documents.models import DocumentExtraction
from app.domain.documents.schemas import (
    ExtractionApplyRequest,
    ExtractionDuplicateResponse,
    ExtractionFieldResponse,
    ExtractionResponse,
)
from app.domain.users.models import User
from app.integrations.ocr.base import OcrProvider
from app.integrations.openrouter.types import LLMNotConfiguredError, LLMProvider
from app.integrations.storage.base import FileStorage

router = APIRouter(prefix="/documents", tags=["documents"])

_NOT_FOUND = "Extração não encontrada."


def _service(
    session: AsyncSession,
    current_user: User,
    provider: LLMProvider,
    storage: FileStorage,
    ocr: OcrProvider,
) -> DocumentExtractionService:
    return DocumentExtractionService(
        session,
        current_user.tenant_id,
        storage=storage,
        runner=AiRunner(session, current_user.tenant_id, provider),
        ocr=ocr,
    )


def _to_response(extraction: DocumentExtraction, *, duplicate: Any = None) -> ExtractionResponse:
    campos = {
        nome: ExtractionFieldResponse(
            value=str(dados.get("value", "")),
            confidence=float(dados.get("confidence", 0)),
            prefill=bool(dados.get("prefill", False)),
            is_valid=bool(dados.get("is_valid", True)),
        )
        for nome, dados in (extraction.extracted or {}).items()
        if isinstance(dados, dict)
    }
    return ExtractionResponse(
        id=extraction.id,
        filename=extraction.filename,
        content_type=extraction.content_type,
        page_count=extraction.page_count,
        document_kind=extraction.document_kind,
        target_type=extraction.target_type,
        used_ocr=extraction.used_ocr,
        ocr_text=extraction.ocr_text,
        fields=campos,
        status=extraction.status,
        action_id=extraction.action_id,
        applied_id=extraction.applied_id,
        model=extraction.model,
        tokens_used=extraction.tokens_used,
        created_at=extraction.created_at,
        duplicate=(
            ExtractionDuplicateResponse(
                customer_id=duplicate.id,
                name=duplicate.name,
                identification=duplicate.identification,
            )
            if duplicate is not None
            else None
        ),
    )


async def _resolve_input(
    file: UploadFile | None,
    attachment_id: uuid.UUID | None,
    *,
    session: AsyncSession,
    storage: FileStorage,
    tenant_id: uuid.UUID,
) -> tuple[bytes, str, str, str, uuid.UUID | None]:
    """As duas origens do documento a extrair: upload novo ou anexo já existente.

    Devolve `(conteúdo, nome, tipo, chave, id do anexo de origem)`. O `origem` é `None`
    no upload porque não há anexo a que se ligar — é a extração que passa a existir
    primeiro, e ligá-la a um anexo inventado seria mentir na auditoria.
    """
    if file is not None:
        content = await file.read()
        content_type = file.content_type or "application/octet-stream"
        storage_key = f"{tenant_id}/extractions/{uuid.uuid4()}"
        await storage.upload(key=storage_key, content=content, content_type=content_type)
        return content, file.filename or "documento", content_type, storage_key, None
    if attachment_id is None:
        raise HTTPException(
            status_code=422, detail="Envie um arquivo ou o id de um anexo existente."
        )
    anexo = await AttachmentRepository(session).get_by_id(attachment_id)
    if anexo is None:
        raise HTTPException(status_code=404, detail="Anexo não encontrado.")
    content = await storage.download(key=anexo.storage_key)
    return content, anexo.filename, anexo.content_type, anexo.storage_key, anexo.id


@router.post("/extract", status_code=201)
async def extract_document(
    file: UploadFile | None = None,
    attachment_id: Annotated[uuid.UUID | None, Form()] = None,
    expected_kind: Annotated[str | None, Form()] = None,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
    storage: FileStorage = Depends(get_file_storage),
    ocr: OcrProvider = Depends(get_ocr_provider),
) -> ExtractionResponse:
    service = _service(session, current_user, provider, storage, ocr)
    entrada = await _resolve_input(
        file, attachment_id, session=session, storage=storage, tenant_id=current_user.tenant_id
    )
    content, filename, content_type, storage_key, origem = entrada

    try:
        extraction = await service.extract(
            user=current_user,
            content=content,
            filename=filename,
            content_type=content_type,
            storage_key=storage_key,
            attachment_id=origem,
            expected_kind=expected_kind,
        )
    except ExtractionTooLargeError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    except UnreadableDocumentError as exc:
        # Regra 10: o texto lido vai junto — é com ele que a pessoa descobre se o
        # problema foi a foto torta ou o documento errado.
        raise HTTPException(
            status_code=422, detail={"detail": exc.detail, "ocr_text": exc.ocr_text}
        ) from exc
    except (LLMNotConfiguredError, FeatureDisabledError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return _to_response(extraction, duplicate=await service.duplicate_of(extraction))


async def _get_extraction(session: AsyncSession, extraction_id: uuid.UUID) -> DocumentExtraction:
    extraction = await session.get(DocumentExtraction, extraction_id)
    if extraction is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return extraction


@router.get("/extractions/{extraction_id}")
async def get_extraction(
    extraction_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
    storage: FileStorage = Depends(get_file_storage),
    ocr: OcrProvider = Depends(get_ocr_provider),
) -> ExtractionResponse:
    extraction = await _get_extraction(session, extraction_id)
    service = _service(session, current_user, provider, storage, ocr)
    return _to_response(extraction, duplicate=await service.duplicate_of(extraction))


@router.post("/extractions/{extraction_id}/apply")
async def apply_extraction(
    extraction_id: uuid.UUID,
    payload: ExtractionApplyRequest,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
    storage: FileStorage = Depends(get_file_storage),
    ocr: OcrProvider = Depends(get_ocr_provider),
) -> ExtractionResponse:
    extraction = await _get_extraction(session, extraction_id)
    service = _service(session, current_user, provider, storage, ocr)
    try:
        acao = await service.apply(
            extraction,
            user=current_user,
            target_type=payload.target_type,
            corrections=payload.corrections,
            arguments=payload.arguments,
        )
    except ExtractionNotPendingError as exc:
        raise HTTPException(
            status_code=409, detail="Esta extração já foi aplicada ou descartada."
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if acao.status == "failed":
        # A execução passa pelo service do domínio (regra 5 da 084): o que reprova um
        # humano reprova a extração, e o motivo é o do domínio, não um 500.
        raise HTTPException(status_code=422, detail=acao.error or "O cadastro foi recusado.")
    return _to_response(extraction)


@router.post("/extractions/{extraction_id}/discard")
async def discard_extraction(
    extraction_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.COLABORADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    provider: LLMProvider = Depends(get_llm_provider),
    storage: FileStorage = Depends(get_file_storage),
    ocr: OcrProvider = Depends(get_ocr_provider),
) -> ExtractionResponse:
    extraction = await _get_extraction(session, extraction_id)
    service = _service(session, current_user, provider, storage, ocr)
    try:
        return _to_response(await service.discard(extraction))
    except ExtractionNotPendingError as exc:
        raise HTTPException(
            status_code=409, detail="Extração já aplicada não pode ser descartada."
        ) from exc

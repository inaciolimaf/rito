import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import get_or_404
from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.monitored_terms.exceptions import (
    InvalidTermStateError,
    SyncAlreadyRunningError,
    TermAlreadyExistsError,
)
from app.domain.monitored_terms.models import MonitoredTerm, TermKind, TermStatus, TermSyncRun
from app.domain.monitored_terms.schemas import (
    MonitoredTermCreateRequest,
    MonitoredTermListResponse,
    MonitoredTermResponse,
    MonitoredTermUpdateRequest,
    TermSyncRunListResponse,
    TermSyncRunResponse,
)
from app.domain.monitored_terms.service import (
    InvalidOabStateError,
    MonitoredTermService,
    ResponsibleUserNotFoundError,
)
from app.domain.users.models import User

router = APIRouter(prefix="/monitored-terms", tags=["monitored-terms"])

_NOT_FOUND_DETAIL = "Termo monitorado não encontrado."


def _term_to_response(term: MonitoredTerm, captured_count: int = 0) -> MonitoredTermResponse:
    return MonitoredTermResponse(
        id=term.id,
        kind=term.kind,
        value=term.value,
        oab_state=term.oab_state,
        label=term.label,
        user_id=term.user_id,
        status=term.status,
        status_message=term.status_message,
        last_sync_at=term.last_sync_at,
        last_success_at=term.last_success_at,
        next_sync_at=term.next_sync_at,
        backfill_from=term.backfill_from,
        is_active=term.is_active,
        created_at=term.created_at,
        captured_count=captured_count,
    )


def _run_to_response(run: TermSyncRun) -> TermSyncRunResponse:
    return TermSyncRunResponse(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        found_count=run.found_count,
        new_count=run.new_count,
        error=run.error,
    )


async def _get_term(service: MonitoredTermService, term_id: uuid.UUID) -> MonitoredTerm:
    return await get_or_404(lambda: service.terms.get_by_id(term_id), _NOT_FOUND_DETAIL)


@router.get("")
async def list_monitored_terms(
    status_: TermStatus | None = Query(default=None, alias="status"),
    kind: TermKind | None = Query(default=None),
    q: str | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MonitoredTermListResponse:
    service = MonitoredTermService(session=session, tenant_id=current_user.tenant_id)
    terms = list(await service.list_terms(status=status_, kind=kind, query=q))
    counts = await service.captured_counts([term.id for term in terms])
    return MonitoredTermListResponse(
        items=[_term_to_response(term, counts.get(term.id, 0)) for term in terms],
        total=len(terms),
    )


@router.post("", status_code=201)
async def create_monitored_term(
    payload: MonitoredTermCreateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MonitoredTermResponse:
    service = MonitoredTermService(session=session, tenant_id=current_user.tenant_id)
    try:
        term = await service.create(payload)
    except TermAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Esse termo já está monitorado.") from exc
    except InvalidOabStateError as exc:
        raise HTTPException(status_code=422, detail="UF da OAB inválida.") from exc
    except ResponsibleUserNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Responsável não encontrado.") from exc
    return _term_to_response(term)


@router.put("/{term_id}")
async def update_monitored_term(
    term_id: uuid.UUID,
    payload: MonitoredTermUpdateRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MonitoredTermResponse:
    service = MonitoredTermService(session=session, tenant_id=current_user.tenant_id)
    term = await _get_term(service, term_id)
    try:
        await service.update(term, payload)
    except ResponsibleUserNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Responsável não encontrado.") from exc
    return _term_to_response(term)


@router.delete("/{term_id}", status_code=204)
async def delete_monitored_term(
    term_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    service = MonitoredTermService(session=session, tenant_id=current_user.tenant_id)
    term = await _get_term(service, term_id)
    await service.delete(term)


@router.post("/{term_id}/sync", status_code=202)
async def sync_monitored_term(
    term_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TermSyncRunResponse:
    """Sync manual (regra 10): abre a execução; o processamento é do worker (044)."""
    service = MonitoredTermService(session=session, tenant_id=current_user.tenant_id)
    term = await _get_term(service, term_id)
    try:
        run = await service.start_manual_sync(term)
    except SyncAlreadyRunningError as exc:
        raise HTTPException(
            status_code=409, detail="Já existe uma sincronização em andamento para esse termo."
        ) from exc
    return _run_to_response(run)


@router.post("/{term_id}/pause")
async def pause_monitored_term(
    term_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MonitoredTermResponse:
    service = MonitoredTermService(session=session, tenant_id=current_user.tenant_id)
    term = await _get_term(service, term_id)
    try:
        await service.pause(term)
    except InvalidTermStateError as exc:
        raise HTTPException(status_code=409, detail="O termo já está pausado.") from exc
    return _term_to_response(term)


@router.post("/{term_id}/resume")
async def resume_monitored_term(
    term_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> MonitoredTermResponse:
    service = MonitoredTermService(session=session, tenant_id=current_user.tenant_id)
    term = await _get_term(service, term_id)
    try:
        await service.resume(term)
    except InvalidTermStateError as exc:
        raise HTTPException(status_code=409, detail="O termo não está pausado.") from exc
    return _term_to_response(term)


@router.get("/{term_id}/runs")
async def list_term_runs(
    term_id: uuid.UUID,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> TermSyncRunListResponse:
    service = MonitoredTermService(session=session, tenant_id=current_user.tenant_id)
    await _get_term(service, term_id)
    rows, next_cursor, total = await service.list_runs(term_id, cursor=cursor, limit=limit)
    return TermSyncRunListResponse(
        items=[_run_to_response(run) for run in rows],
        next_cursor=next_cursor,
        total=total,
    )

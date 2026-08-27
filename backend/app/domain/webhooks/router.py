"""Rotas de webhook (spec 093 §6)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import UserRole, require_role
from app.domain.auth.deps import get_session_for_current_user
from app.domain.users.models import User
from app.domain.webhooks.models import WebhookDelivery, WebhookEndpoint
from app.domain.webhooks.schemas import (
    DeliveryListResponse,
    DeliveryResponse,
    EndpointListResponse,
    EndpointRequest,
    EndpointResponse,
    TestEndpointRequest,
)
from app.domain.webhooks.sender import WebhookSender
from app.domain.webhooks.service import EndpointInactiveError, WebhookService
from app.domain.webhooks.ssrf import UnsafeUrlError

router = APIRouter(tags=["webhooks"])

_ENDPOINT_NOT_FOUND = "Webhook não encontrado."
_DELIVERY_NOT_FOUND = "Entrega não encontrada."


async def get_webhook_sender(request: Request) -> WebhookSender:
    """Montado uma vez no lifespan — nenhuma rota abre client HTTP."""
    sender: WebhookSender = request.app.state.webhook_sender
    return sender


def _to_endpoint(endpoint: WebhookEndpoint, *, secret: str | None = None) -> EndpointResponse:
    return EndpointResponse(
        id=endpoint.id,
        name=endpoint.name,
        url=endpoint.url,
        headers=dict(endpoint.headers or {}),
        is_active=endpoint.is_active,
        failure_streak=endpoint.failure_streak,
        disabled_at=endpoint.disabled_at,
        created_at=endpoint.created_at,
        secret=secret,
    )


def _to_delivery(delivery: WebhookDelivery) -> DeliveryResponse:
    return DeliveryResponse(
        id=delivery.id,
        endpoint_id=delivery.endpoint_id,
        run_id=delivery.run_id,
        event_kind=delivery.event_kind,
        payload=delivery.payload,
        attempt=delivery.attempt,
        status_code=delivery.status_code,
        response_body=delivery.response_body,
        duration_ms=delivery.duration_ms,
        error=delivery.error,
        delivered_at=delivery.delivered_at,
        next_attempt_at=delivery.next_attempt_at,
        created_at=delivery.created_at,
    )


def _service(session: AsyncSession, current_user: User, sender: WebhookSender) -> WebhookService:
    return WebhookService(session, current_user.tenant_id, sender=sender)


async def _get_endpoint(session: AsyncSession, endpoint_id: uuid.UUID) -> WebhookEndpoint:
    endpoint = await session.get(WebhookEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail=_ENDPOINT_NOT_FOUND)
    return endpoint


@router.get("/webhook-endpoints")
async def list_endpoints(
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    sender: WebhookSender = Depends(get_webhook_sender),
) -> EndpointListResponse:
    service = _service(session, current_user, sender)
    endpoints = await service.endpoints.list_all()
    # Sem `secret`: a listagem nunca devolve o segredo (regra 8).
    return EndpointListResponse(
        items=[_to_endpoint(endpoint) for endpoint in endpoints], total=len(endpoints)
    )


@router.post("/webhook-endpoints", status_code=201)
async def create_endpoint(
    payload: EndpointRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    sender: WebhookSender = Depends(get_webhook_sender),
) -> EndpointResponse:
    service = _service(session, current_user, sender)
    try:
        endpoint, segredo = await service.create(
            name=payload.name, url=payload.url, headers=payload.headers
        )
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    return _to_endpoint(endpoint, secret=segredo)


@router.put("/webhook-endpoints/{endpoint_id}")
async def update_endpoint(
    endpoint_id: uuid.UUID,
    payload: EndpointRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    sender: WebhookSender = Depends(get_webhook_sender),
) -> EndpointResponse:
    service = _service(session, current_user, sender)
    endpoint = await _get_endpoint(session, endpoint_id)
    try:
        await service.update(endpoint, name=payload.name, url=payload.url, headers=payload.headers)
    except UnsafeUrlError as exc:
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    return _to_endpoint(endpoint)


@router.delete("/webhook-endpoints/{endpoint_id}", status_code=204)
async def delete_endpoint(
    endpoint_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
) -> None:
    endpoint = await _get_endpoint(session, endpoint_id)
    await session.delete(endpoint)


@router.post("/webhook-endpoints/{endpoint_id}/rotate-secret")
async def rotate_secret(
    endpoint_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    sender: WebhookSender = Depends(get_webhook_sender),
) -> EndpointResponse:
    service = _service(session, current_user, sender)
    endpoint = await _get_endpoint(session, endpoint_id)
    return _to_endpoint(endpoint, secret=await service.rotate_secret(endpoint))


@router.post("/webhook-endpoints/{endpoint_id}/reactivate")
async def reactivate_endpoint(
    endpoint_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    sender: WebhookSender = Depends(get_webhook_sender),
) -> EndpointResponse:
    service = _service(session, current_user, sender)
    endpoint = await _get_endpoint(session, endpoint_id)
    return _to_endpoint(await service.reactivate(endpoint))


@router.post("/webhook-endpoints/{endpoint_id}/test")
async def test_endpoint(
    endpoint_id: uuid.UUID,
    payload: TestEndpointRequest,
    current_user: User = Depends(require_role(UserRole.GESTOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    sender: WebhookSender = Depends(get_webhook_sender),
) -> DeliveryResponse:
    """Regra 9: manda um payload de exemplo e mostra a resposta completa."""
    service = _service(session, current_user, sender)
    endpoint = await _get_endpoint(session, endpoint_id)
    try:
        delivery = await service.dispatch(
            endpoint, event=payload.event, trigger_payload=payload.payload
        )
    except EndpointInactiveError as exc:
        raise HTTPException(
            status_code=409, detail="Este webhook está desativado. Reative antes de testar."
        ) from exc
    return _to_delivery(delivery)


@router.get("/webhook-deliveries")
async def list_deliveries(
    endpoint_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(delivered|failed)$"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    sender: WebhookSender = Depends(get_webhook_sender),
) -> DeliveryListResponse:
    service = _service(session, current_user, sender)
    entregas = await service.deliveries.list_for(
        endpoint_id=endpoint_id, only_failed=status == "failed", limit=limit
    )
    if status == "delivered":
        entregas = [item for item in entregas if item.delivered_at is not None]
    return DeliveryListResponse(
        items=[_to_delivery(item) for item in entregas], total=len(entregas)
    )


@router.post("/webhook-deliveries/{delivery_id}/retry")
async def retry_delivery(
    delivery_id: uuid.UUID,
    current_user: User = Depends(require_role(UserRole.ADMINISTRADOR)),
    session: AsyncSession = Depends(get_session_for_current_user),
    sender: WebhookSender = Depends(get_webhook_sender),
) -> DeliveryResponse:
    service = _service(session, current_user, sender)
    delivery = await session.get(WebhookDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail=_DELIVERY_NOT_FOUND)
    try:
        return _to_delivery(await service.retry(delivery))
    except EndpointInactiveError as exc:
        raise HTTPException(
            status_code=409, detail="Este webhook está desativado. Reative antes de reenviar."
        ) from exc

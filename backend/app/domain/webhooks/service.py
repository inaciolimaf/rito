"""Envio, retry e diagnóstico de webhooks (spec 093).

Três coisas que este arquivo não faz, e cada uma é uma decisão:

- **não interpreta a resposta** (regra 1): 2xx é entrega e acabou. Webhook que exige
  resposta de negócio vira acoplamento — o Rito passaria a depender do n8n do escritório
  estar de pé para concluir uma tarefa;
- **não retenta dentro da request** (regra 3): o backoff é de 1, 5 e 15 minutos, e
  segurar a request do usuário por 21 minutos seria absurdo. A tentativa fica marcada
  com `next_attempt_at` e quem volta é o worker;
- **não confia na URL guardada**: a peneira de SSRF roda a cada envio, não só ao salvar.
  DNS muda depois do cadastro, e é justamente essa a jogada do atacante paciente.
"""

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.invariants import not_none
from app.core.observability.metrics import record_webhook_delivery
from app.core.repository import BaseRepository
from app.domain.integration_alerts.models import IntegrationAlert
from app.domain.webhooks.models import WebhookDelivery, WebhookEndpoint
from app.domain.webhooks.payloads import build_payload
from app.domain.webhooks.sender import SendResult, WebhookSender
from app.domain.webhooks.signature import (
    DELIVERY_HEADER,
    EVENT_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    generate_secret,
    sign,
)
from app.domain.webhooks.ssrf import UnsafeUrlError, validate_webhook_url

# Regra 3: três tentativas, backoff de 1, 5 e 15 minutos.
BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15))
MAX_ATTEMPTS = len(BACKOFF) + 1
# Regra 5: o corpo da resposta é diagnóstico, não arquivo — 10 KB resolve qualquer erro
# que um servidor devolva em texto, e evita guardar um HTML de 2 MB por entrega.
MAX_RESPONSE_BYTES = 10 * 1024
# Regra 10.
MAX_FAILURE_STREAK = 20
# Regra 12.
RETENTION_DAYS = 30

_ALERT_INTEGRATION = "webhooks"
_ALERT_CODE = "endpoint_disabled"


class EndpointInactiveError(Exception):
    """Endpoint desativado não recebe envio — nem manual."""


class WebhookEndpointRepository(BaseRepository[WebhookEndpoint]):
    model = WebhookEndpoint

    async def get_by_name(self, name: str) -> WebhookEndpoint | None:
        stmt = select(WebhookEndpoint).where(WebhookEndpoint.name == name)
        return (await self.session.scalars(stmt)).first()

    async def list_all(self) -> list[WebhookEndpoint]:
        stmt = select(WebhookEndpoint).order_by(WebhookEndpoint.created_at.desc())
        return list((await self.session.scalars(stmt)).all())


class WebhookDeliveryRepository(BaseRepository[WebhookDelivery]):
    model = WebhookDelivery

    async def list_for(
        self,
        *,
        endpoint_id: uuid.UUID | None = None,
        only_failed: bool = False,
        limit: int = 50,
    ) -> list[WebhookDelivery]:
        stmt = select(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(limit)
        if endpoint_id is not None:
            stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
        if only_failed:
            stmt = stmt.where(WebhookDelivery.delivered_at.is_(None))
        return list((await self.session.scalars(stmt)).all())

    async def due(self, *, now: datetime, limit: int = 100) -> list[WebhookDelivery]:
        stmt = (
            select(WebhookDelivery)
            .where(
                WebhookDelivery.delivered_at.is_(None),
                WebhookDelivery.next_attempt_at.is_not(None),
                WebhookDelivery.next_attempt_at <= now,
            )
            .order_by(WebhookDelivery.next_attempt_at)
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())


class WebhookService:
    def __init__(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        *,
        sender: WebhookSender,
        now: datetime | None = None,
    ) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.sender = sender
        self.endpoints = WebhookEndpointRepository(session)
        self.deliveries = WebhookDeliveryRepository(session)
        self._now = now

    def now(self) -> datetime:
        return self._now or datetime.now(UTC)

    @property
    def allow_local(self) -> bool:
        """Regra 6: HTTP e localhost só fora de produção."""
        return get_settings().app_env != "production"

    # ------------------------------------------------------------------- CRUD

    async def create(
        self, *, name: str, url: str, headers: dict[str, str]
    ) -> tuple[WebhookEndpoint, str]:
        """Devolve o endpoint e o segredo em claro — é a única vez que ele existe
        legível (regra 8), e quem chama é responsável por mostrá-lo uma vez."""
        validate_webhook_url(url, allow_local=self.allow_local)
        segredo = generate_secret()
        endpoint = WebhookEndpoint(
            tenant_id=self.tenant_id, name=name, url=url, secret=segredo, headers=headers
        )
        self.session.add(endpoint)
        await self.session.flush()
        return endpoint, segredo

    async def update(
        self, endpoint: WebhookEndpoint, *, name: str, url: str, headers: dict[str, str]
    ) -> WebhookEndpoint:
        validate_webhook_url(url, allow_local=self.allow_local)
        endpoint.name = name
        endpoint.url = url
        endpoint.headers = headers
        await self.session.flush()
        return endpoint

    async def rotate_secret(self, endpoint: WebhookEndpoint) -> str:
        segredo = generate_secret()
        endpoint.secret = segredo
        await self.session.flush()
        return segredo

    async def reactivate(self, endpoint: WebhookEndpoint) -> WebhookEndpoint:
        endpoint.is_active = True
        endpoint.disabled_at = None
        endpoint.failure_streak = 0
        await self.session.flush()
        return endpoint

    # ----------------------------------------------------------------- envio

    async def dispatch(
        self,
        endpoint: WebhookEndpoint,
        *,
        event: str,
        trigger_payload: dict[str, Any],
        run_id: uuid.UUID | None = None,
    ) -> WebhookDelivery:
        """Monta o payload do contrato e tenta entregar uma vez."""
        if not endpoint.is_active:
            raise EndpointInactiveError
        corpo = await build_payload(
            self.session,
            event=event,
            tenant_id=self.tenant_id,
            trigger_payload=trigger_payload,
            occurred_at=self.now(),
        )
        delivery = WebhookDelivery(
            tenant_id=self.tenant_id,
            endpoint_id=endpoint.id,
            run_id=run_id,
            event_kind=event,
            payload=corpo,
        )
        self.session.add(delivery)
        await self.session.flush()
        return await self.attempt(delivery, endpoint=endpoint)

    async def attempt(
        self, delivery: WebhookDelivery, *, endpoint: WebhookEndpoint | None = None
    ) -> WebhookDelivery:
        if endpoint is None:
            endpoint = await self.endpoints.get_by_id(delivery.endpoint_id)
        endpoint = not_none(endpoint, "a entrega referencia um endpoint existente (FK)")

        corpo = json.dumps(delivery.payload, ensure_ascii=False).encode("utf-8")
        agora = self.now()
        try:
            destino = validate_webhook_url(endpoint.url, allow_local=self.allow_local)
        except UnsafeUrlError as exc:
            return await self._register(
                delivery,
                endpoint,
                SendResult(status_code=None, body="", duration_ms=0, error=exc.detail),
                retryable=False,
            )

        resultado = await self.sender.send(
            url=destino,
            body=corpo,
            headers=self._headers(endpoint, delivery, corpo, agora),
            allow_local=self.allow_local,
        )
        return await self._register(delivery, endpoint, resultado, retryable=resultado.retryable)

    def _headers(
        self,
        endpoint: WebhookEndpoint,
        delivery: WebhookDelivery,
        body: bytes,
        agora: datetime,
    ) -> dict[str, str]:
        timestamp = int(agora.timestamp())
        cabecalhos = {
            "Content-Type": "application/json",
            "User-Agent": "Rito-Webhooks/1",
            EVENT_HEADER: delivery.event_kind,
            DELIVERY_HEADER: str(delivery.id),
            TIMESTAMP_HEADER: str(timestamp),
            SIGNATURE_HEADER: sign(secret=endpoint.secret, body=body, timestamp=timestamp),
        }
        # Cabeçalho do escritório não sobrescreve a assinatura: quem configurou um
        # `X-Rito-Signature` próprio, por engano ou não, não pode desligar a validação.
        for chave, valor in (endpoint.headers or {}).items():
            if chave.lower() not in {item.lower() for item in cabecalhos}:
                cabecalhos[str(chave)] = str(valor)
        return cabecalhos

    async def _register(
        self,
        delivery: WebhookDelivery,
        endpoint: WebhookEndpoint,
        resultado: SendResult,
        *,
        retryable: bool,
    ) -> WebhookDelivery:
        delivery.status_code = resultado.status_code
        delivery.response_body = resultado.body[:MAX_RESPONSE_BYTES] if resultado.body else None
        delivery.duration_ms = resultado.duration_ms
        delivery.error = resultado.error[:500] if resultado.error else None

        vai_retentar = retryable and delivery.attempt < MAX_ATTEMPTS
        # Spec 097, regra 6: entregas de webhook por desfecho. Aqui, no único ponto por onde
        # toda tentativa (primeira ou retry) passa.
        record_webhook_delivery(
            status="delivered" if resultado.ok else ("retrying" if vai_retentar else "failed")
        )
        if resultado.ok:
            delivery.delivered_at = self.now()
            delivery.next_attempt_at = None
            # Regra 10: a sequência de falhas zera na primeira entrega boa.
            endpoint.failure_streak = 0
        else:
            await self._schedule_retry(delivery, endpoint, vai_retentar)
        await self.session.flush()
        return delivery

    async def _schedule_retry(
        self, delivery: WebhookDelivery, endpoint: WebhookEndpoint, vai_retentar: bool
    ) -> None:
        """Agenda a próxima tentativa, ou desiste — e conta a falha para o endpoint.

        O contador de falhas é do ENDPOINT e não da entrega: uma entrega que esgotou as
        tentativas é um evento perdido, mas um endpoint com muitas falhas seguidas é um
        destino quebrado, e é ele que precisa ser desligado (regra 10) para o Rito parar de
        gastar tentativas contra uma URL que não existe mais.
        """
        delivery.next_attempt_at = (
            self.now() + BACKOFF[delivery.attempt - 1] if vai_retentar else None
        )
        endpoint.failure_streak += 1
        if endpoint.failure_streak >= MAX_FAILURE_STREAK and endpoint.is_active:
            await self._disable(endpoint)

    async def _disable(self, endpoint: WebhookEndpoint) -> None:
        """Regra 10: vinte falhas seguidas é destino morto — e desativar em silêncio
        seria trocar um problema visível por um invisível."""
        endpoint.is_active = False
        endpoint.disabled_at = self.now()
        self.session.add(
            IntegrationAlert(
                tenant_id=self.tenant_id,
                integration=_ALERT_INTEGRATION,
                severity="critical",
                code=_ALERT_CODE,
                message=(
                    f"O webhook '{endpoint.name}' foi desativado depois de "
                    f"{MAX_FAILURE_STREAK} falhas seguidas. Confira a URL e reative."
                ),
            )
        )

    async def retry(self, delivery: WebhookDelivery) -> WebhookDelivery:
        """Regra 11: o reenvio usa o payload ORIGINAL.

        Remontar a partir do estado atual mandaria dados diferentes dos do momento do
        evento — o que transforma "reenviar" em "mandar outra coisa", e é justamente o
        que quebra a conciliação do outro lado.
        """
        endpoint = await self.endpoints.get_by_id(delivery.endpoint_id)
        endpoint = not_none(endpoint, "a entrega referencia um endpoint existente (FK)")
        if not endpoint.is_active:
            raise EndpointInactiveError
        nova = WebhookDelivery(
            tenant_id=self.tenant_id,
            endpoint_id=delivery.endpoint_id,
            run_id=delivery.run_id,
            event_kind=delivery.event_kind,
            payload=delivery.payload,
            attempt=1,
        )
        self.session.add(nova)
        await self.session.flush()
        return await self.attempt(nova, endpoint=endpoint)

    async def retry_due(self, *, limit: int = 100) -> int:
        pendentes = await self.deliveries.due(now=self.now(), limit=limit)
        for delivery in pendentes:
            delivery.attempt += 1
            await self.attempt(delivery)
        return len(pendentes)

    async def purge_old(self) -> int:
        """Regra 12: 30 dias. Log de entrega velho não ajuda ninguém e pesa na tabela."""
        corte = self.now() - timedelta(days=RETENTION_DAYS)
        antigas = list(
            (
                await self.session.scalars(
                    select(WebhookDelivery.id).where(WebhookDelivery.created_at < corte)
                )
            ).all()
        )
        if antigas:
            await self.session.execute(
                delete(WebhookDelivery).where(WebhookDelivery.id.in_(antigas))
            )
        return len(antigas)

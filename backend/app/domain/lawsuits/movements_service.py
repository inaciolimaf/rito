"""Movimentações e timeline do processo (spec 026) — caso de uso separado de
`LawsuitService` na refatoração 030 (SRP)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.lawsuits.exceptions import (
    MovementNotAuthorError,
    TribunalMovementImmutableError,
)
from app.domain.lawsuits.models import Lawsuit, LawsuitMovement, MovementOrigin
from app.domain.lawsuits.repository import (
    LawsuitMovementRepository,
    TimelineRow,
    decode_timeline_cursor,
    encode_timeline_cursor,
)
from app.domain.lawsuits.schemas import MovementCreateRequest, MovementUpdateRequest
from app.domain.users.models import User, UserRole


@dataclass
class TimelinePage:
    items: Sequence[TimelineRow]
    next_cursor: str | None
    total: int


class MovementsService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.tenant_id = tenant_id
        self.movements = LawsuitMovementRepository(session)

    async def list_timeline(
        self,
        lawsuit_id: uuid.UUID,
        *,
        kinds: Sequence[str],
        cursor: str | None,
        limit: int,
    ) -> TimelinePage:
        decoded = decode_timeline_cursor(cursor) if cursor else None
        items, total = await self.movements.list_timeline(
            lawsuit_id, kinds=kinds, cursor=decoded, limit=limit
        )
        next_cursor = (
            encode_timeline_cursor(items[-1].occurred_at, items[-1].kind, items[-1].id)
            if len(items) == limit
            else None
        )
        return TimelinePage(items=items, next_cursor=next_cursor, total=total)

    async def create_movement(
        self, lawsuit: Lawsuit, payload: MovementCreateRequest, author: User
    ) -> LawsuitMovement:
        return await self.movements.create(
            LawsuitMovement(
                tenant_id=self.tenant_id,
                lawsuit_id=lawsuit.id,
                origin=MovementOrigin.MANUAL,
                occurred_at=payload.occurred_at,
                title=payload.title,
                body=payload.body,
                created_by=author.id,
            )
        )

    def check_movement_editable(self, movement: LawsuitMovement, actor: User) -> None:
        # Regra 3: movimentação do tribunal é imutável pela UI.
        if movement.origin != MovementOrigin.MANUAL:
            raise TribunalMovementImmutableError
        # Regra 4: só o autor ou um ADMINISTRADOR edita/exclui.
        if movement.created_by != actor.id and actor.role != UserRole.ADMINISTRADOR:
            raise MovementNotAuthorError

    async def update_movement(
        self, movement: LawsuitMovement, payload: MovementUpdateRequest, actor: User
    ) -> LawsuitMovement:
        self.check_movement_editable(movement, actor)
        movement.occurred_at = payload.occurred_at
        movement.title = payload.title
        movement.body = payload.body
        return movement

    async def delete_movement(self, movement: LawsuitMovement, actor: User) -> None:
        self.check_movement_editable(movement, actor)
        await self.movements.delete(movement)

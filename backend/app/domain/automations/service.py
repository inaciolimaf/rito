"""CRUD de automações (spec 092 §5).

O service existe para uma coisa que o CRUD genérico não faz: validar a automação INTEIRA
antes de salvar. Gatilho desconhecido, ação desconhecida, condição malformada e a 21ª
ação são erros de configuração — e erro de configuração precisa aparecer na tela de quem
está configurando, não seis semanas depois numa execução silenciosa.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import BaseRepository
from app.domain.automations.conditions import InvalidConditionError, validate_condition
from app.domain.automations.engine import MAX_ACTIONS, AutomationLimitError
from app.domain.automations.models import (
    ActionKind,
    Automation,
    AutomationAction,
    AutomationRun,
    AutomationRunStep,
    DelayKind,
    TriggerKind,
)

_TRIGGERS = {item.value for item in TriggerKind}
_ACTIONS = {item.value for item in ActionKind}
_DELAYS = {item.value for item in DelayKind}


class UnknownTriggerError(Exception):
    pass


class UnknownActionKindError(Exception):
    pass


class AutomationNameConflictError(Exception):
    pass


@dataclass(frozen=True)
class ActionInput:
    action_kind: str
    action_config: dict[str, Any]
    delay_kind: str = DelayKind.IMMEDIATE.value
    delay_value: int | None = None
    condition: dict[str, Any] | None = None


class AutomationRepository(BaseRepository[Automation]):
    model = Automation

    async def get_by_name(self, name: str) -> Automation | None:
        return (
            await self.session.scalars(select(Automation).where(Automation.name == name))
        ).first()

    async def list_all(self, *, only_active: bool | None = None) -> list[Automation]:
        stmt = select(Automation).order_by(Automation.created_at.desc())
        if only_active is not None:
            stmt = stmt.where(Automation.is_active.is_(only_active))
        return list((await self.session.scalars(stmt)).all())


class AutomationService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.automations = AutomationRepository(session)

    async def create(
        self,
        *,
        name: str,
        description: str | None,
        trigger_kind: str,
        trigger_config: dict[str, Any],
        actions: list[ActionInput],
        created_by: uuid.UUID,
    ) -> Automation:
        self._validate(trigger_kind, actions)
        if await self.automations.get_by_name(name) is not None:
            raise AutomationNameConflictError
        automation = Automation(
            tenant_id=self.tenant_id,
            name=name,
            description=description,
            trigger_kind=trigger_kind,
            trigger_config=trigger_config,
            created_by=created_by,
        )
        self.session.add(automation)
        await self.session.flush()
        await self._replace_actions(automation, actions)
        return automation

    async def update(
        self,
        automation: Automation,
        *,
        name: str,
        description: str | None,
        trigger_kind: str,
        trigger_config: dict[str, Any],
        actions: list[ActionInput],
    ) -> Automation:
        self._validate(trigger_kind, actions)
        existente = await self.automations.get_by_name(name)
        if existente is not None and existente.id != automation.id:
            raise AutomationNameConflictError
        automation.name = name
        automation.description = description
        automation.trigger_kind = trigger_kind
        automation.trigger_config = trigger_config
        await self._replace_actions(automation, actions)
        return automation

    async def toggle(self, automation: Automation, *, is_active: bool) -> Automation:
        """Regra 11: desativar não afeta execução em andamento. O motor só consulta
        `is_active` na hora de ABRIR uma execução — quem já começou, termina."""
        automation.is_active = is_active
        await self.session.flush()
        return automation

    async def actions_of(self, automation: Automation) -> list[AutomationAction]:
        stmt = (
            select(AutomationAction)
            .where(AutomationAction.automation_id == automation.id)
            .order_by(AutomationAction.position)
        )
        return list((await self.session.scalars(stmt)).all())

    async def runs_of(self, automation: Automation, *, limit: int = 50) -> list[AutomationRun]:
        stmt = (
            select(AutomationRun)
            .where(AutomationRun.automation_id == automation.id)
            .order_by(AutomationRun.started_at.desc())
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def steps_of(self, run: AutomationRun) -> list[AutomationRunStep]:
        stmt = (
            select(AutomationRunStep)
            .where(AutomationRunStep.run_id == run.id)
            .order_by(AutomationRunStep.position)
        )
        return list((await self.session.scalars(stmt)).all())

    async def _replace_actions(self, automation: Automation, actions: list[ActionInput]) -> None:
        await self.session.execute(
            delete(AutomationAction).where(AutomationAction.automation_id == automation.id)
        )
        for posicao, entrada in enumerate(actions):
            self.session.add(
                AutomationAction(
                    tenant_id=self.tenant_id,
                    automation_id=automation.id,
                    position=posicao,
                    action_kind=entrada.action_kind,
                    action_config=entrada.action_config,
                    delay_kind=entrada.delay_kind,
                    delay_value=entrada.delay_value,
                    condition=entrada.condition,
                )
            )
        await self.session.flush()

    def _validate(self, trigger_kind: str, actions: list[ActionInput]) -> None:
        if trigger_kind not in _TRIGGERS:
            raise UnknownTriggerError(trigger_kind)
        if len(actions) > MAX_ACTIONS:
            # Regra 13: passou de 20, deixou de ser regra e virou programa.
            raise AutomationLimitError(f"Uma automação aceita no máximo {MAX_ACTIONS} ações.")
        for entrada in actions:
            if entrada.action_kind not in _ACTIONS:
                raise UnknownActionKindError(entrada.action_kind)
            if entrada.delay_kind not in _DELAYS:
                raise UnknownActionKindError(entrada.delay_kind)
            validate_condition(entrada.condition)


__all__ = [
    "ActionInput",
    "AutomationLimitError",
    "AutomationNameConflictError",
    "AutomationRepository",
    "AutomationService",
    "InvalidConditionError",
    "UnknownActionKindError",
    "UnknownTriggerError",
]

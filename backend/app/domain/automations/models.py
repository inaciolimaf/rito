"""Tabelas do motor de automação (spec 092 §4)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    SmallInteger,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TenantMixin


class TriggerKind(StrEnum):
    """Os 5 eventos que abrem uma automação (regra 1).

    A lista é fechada de propósito: cada gatilho tem um ponto no código que o emite, e um
    gatilho sem emissor seria uma automação que nunca roda — pior que não existir, porque
    o escritório acha que configurou proteção."""

    TASK_COMPLETED = "task.completed"
    LAWSUIT_STAGE_CHANGED = "lawsuit.stage_changed"
    LAWSUIT_CREATED = "lawsuit.created"
    PUBLICATION_RECEIVED = "publication.received"
    TRANSACTION_OVERDUE = "transaction.overdue"


class ActionKind(StrEnum):
    CREATE_TASK = "create_task"
    SET_ASSIGNEE = "set_assignee"
    CHANGE_STAGE = "change_stage"
    NOTIFY = "notify"
    WAIT_CONDITION = "wait_condition"


class DelayKind(StrEnum):
    IMMEDIATE = "immediate"
    BUSINESS_DAYS = "business_days"
    CALENDAR_DAYS = "calendar_days"
    AFTER_PREVIOUS = "after_previous"


class RunStatus(StrEnum):
    RUNNING = "running"
    WAITING = "waiting"
    DONE = "done"
    FAILED = "failed"


class StepStatus(StrEnum):
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


class Automation(TenantMixin, Base):
    """Uma regra do escritório: quando ISTO acontecer, faça AQUILO (spec 092)."""

    __tablename__ = "automations"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_automations_name"),)

    name: Mapped[str]
    description: Mapped[str | None] = mapped_column(default=None)
    trigger_kind: Mapped[str]
    # Regra 2: restringe o gatilho — "tarefa concluída" pode valer só para um tipo.
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    # Regra 12: a escrita roda com as permissões de QUEM CRIOU a automação, não de quem
    # por acaso disparou o evento — senão a mesma regra faria coisas diferentes conforme
    # quem mexeu no processo.
    created_by: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class AutomationAction(TenantMixin, Base):
    """Um passo da sequência (regra 3): o que fazer, quando, e sob qual condição."""

    __tablename__ = "automation_actions"
    __table_args__ = (
        UniqueConstraint("automation_id", "position", name="uq_automation_actions_position"),
        CheckConstraint(
            "delay_kind IN ('immediate', 'business_days', 'calendar_days', 'after_previous')",
            name="ck_automation_actions_delay_kind",
        ),
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("automations.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(SmallInteger())
    action_kind: Mapped[str]
    action_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    delay_kind: Mapped[str] = mapped_column(
        default=DelayKind.IMMEDIATE.value, server_default=text("'immediate'")
    )
    delay_value: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    condition: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)


class AutomationRun(TenantMixin, Base):
    """Uma execução. `next_position` + `next_action_at`/`waiting_on_id` são onde ela
    parou — é com isso que o worker sabe o que retomar e quando."""

    __tablename__ = "automation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'waiting', 'done', 'failed')",
            name="ck_automation_runs_status",
        ),
    )

    automation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("automations.id", ondelete="CASCADE")
    )
    trigger_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    subject_type: Mapped[str | None] = mapped_column(default=None)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    status: Mapped[str] = mapped_column(
        default=RunStatus.RUNNING.value, server_default=text("'running'")
    )
    actions_completed: Mapped[int] = mapped_column(
        SmallInteger(), default=0, server_default=text("0")
    )
    chain_depth: Mapped[int] = mapped_column(SmallInteger(), default=0, server_default=text("0"))
    next_position: Mapped[int | None] = mapped_column(SmallInteger(), default=None)
    next_action_at: Mapped[datetime | None] = mapped_column(default=None)
    waiting_on_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(default=None)


class AutomationRunStep(TenantMixin, Base):
    """O que aconteceu em cada passo — inclusive o que foi PULADO (regra 6).

    A unicidade de `(run_id, position)` é a regra 8 escrita no banco: reprocessar não
    duplica porque o banco não deixa, não porque o código lembrou de conferir.
    """

    __tablename__ = "automation_run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "position", name="uq_automation_run_steps_position"),
        CheckConstraint(
            "status IN ('done', 'skipped', 'failed')", name="ck_automation_run_steps_status"
        ),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("automation_runs.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(SmallInteger())
    action_kind: Mapped[str]
    status: Mapped[str]
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    error: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

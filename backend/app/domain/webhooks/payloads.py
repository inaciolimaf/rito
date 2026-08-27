"""Payloads padronizados por gatilho (spec 093 §5).

O contrato é público: o n8n do escritório vai ler estas chaves, e mudar o nome de uma
delas quebra a automação de quem já integrou. Por isso o formato mora aqui, num arquivo
só, e não espalhado em quem dispara — e por isso existe um teste que compara o payload
com o contrato campo a campo.

A forma segue o levantamento do Flowter (`docs/ADVBOX-ESPECIFICACAO-COMPLETA.md` §8):
evento no topo, e o objeto do domínio aninhado com o processo e os clientes junto. É mais
verboso do que mandar só os ids — e é isso que faz o webhook ser útil sem o outro lado
precisar chamar a API de volta para cada campo.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.customers.models import Customer
from app.domain.lawsuits.models import Lawsuit, LawsuitParty
from app.domain.posts.models import Post, PostUser
from app.domain.stages.models import Stage
from app.domain.task_types.models import TaskType
from app.domain.users.models import User


async def build_payload(
    session: AsyncSession,
    *,
    event: str,
    tenant_id: uuid.UUID,
    trigger_payload: dict[str, Any],
    occurred_at: datetime | None = None,
) -> dict[str, Any]:
    corpo: dict[str, Any] = {
        "event": event,
        "occurred_at": (occurred_at or datetime.now(UTC)).isoformat(),
        "tenant_id": str(tenant_id),
    }
    if event == "task.completed":
        corpo.update(await _task_completed(session, trigger_payload))
    elif event == "lawsuit.stage_changed":
        corpo.update(await _stage_changed(session, trigger_payload))
    else:
        # Gatilho sem contrato próprio manda o payload cru — melhor que não mandar nada,
        # e o `event` diz ao outro lado o que esperar.
        corpo["data"] = trigger_payload
    return corpo


async def _task_completed(session: AsyncSession, trigger: dict[str, Any]) -> dict[str, Any]:
    post = await _get(session, Post, trigger.get("post_id"))
    if post is None:
        return {"data": trigger}
    task_type = await session.get(TaskType, post.task_type_id)
    linhas = list(
        (await session.scalars(select(PostUser).where(PostUser.post_id == post.id))).all()
    )
    nomes = await _user_names(session, [linha.user_id for linha in linhas])
    return {
        "task": {
            "id": str(post.id),
            "title": task_type.name if task_type else None,
            "notes": post.comments,
            "location": post.location,
            "scheduled_date": _iso(post.scheduled_date),
            "deadline_date": _iso(post.deadline_date),
            "completed_at": _iso(
                max((linha.completed_at for linha in linhas if linha.completed_at), default=None)
            ),
            "points": post.reward_snapshot,
        },
        "lawsuit": await _lawsuit_block(session, post.lawsuit_id),
        "users": [
            {
                "id": str(linha.user_id),
                "name": nomes.get(linha.user_id),
                "completed_at": _iso(linha.completed_at),
                # `important`/`urgent` são da TAREFA (spec 032), não da linha do
                # responsável; o contrato do Flowter os traz por usuário, e mandar o
                # valor da tarefa em cada linha é o mais fiel possível sem inventar um
                # campo que o Rito não tem.
                "important": post.is_important,
                "urgent": post.is_urgent,
            }
            for linha in linhas
        ],
    }


async def _stage_changed(session: AsyncSession, trigger: dict[str, Any]) -> dict[str, Any]:
    lawsuit_id = trigger.get("lawsuit_id")
    bloco = await _lawsuit_block(session, lawsuit_id)
    if bloco is None:
        return {"data": trigger}
    bloco["from_stage"] = await _stage_name(session, trigger.get("from_stage_id"))
    bloco["to_stage"] = await _stage_name(session, trigger.get("stage_id"))
    autor_id = trigger.get("changed_by")
    autor = await _get(session, User, autor_id)
    return {
        "lawsuit": bloco,
        "changed_by": ({"id": str(autor.id), "name": autor.name} if autor is not None else None),
    }


async def _lawsuit_block(session: AsyncSession, lawsuit_id: Any) -> dict[str, Any] | None:
    lawsuit = await _get(session, Lawsuit, lawsuit_id)
    if lawsuit is None:
        return None
    etapa = await _stage_name(session, lawsuit.stage_id)
    partes = list(
        (
            await session.scalars(
                select(LawsuitParty).where(
                    LawsuitParty.lawsuit_id == lawsuit.id, LawsuitParty.is_client.is_(True)
                )
            )
        ).all()
    )
    clientes = []
    for parte in partes:
        customer = await session.get(Customer, parte.customer_id)
        if customer is None:  # pragma: no cover - FK garante
            continue
        clientes.append(
            {
                "id": str(customer.id),
                "name": customer.name,
                "identification": customer.identification,
                "origin": str(customer.origin_id) if customer.origin_id else None,
                "cellphone": customer.cellphone,
                "phone": customer.phone,
                "email": customer.email,
            }
        )
    return {
        "id": str(lawsuit.id),
        "process_number": lawsuit.process_number,
        "protocol_number": lawsuit.protocol_number,
        "notes": lawsuit.notes,
        "stage": etapa,
        "responsible_id": str(lawsuit.user_id),
        "customers": clientes,
    }


async def _stage_name(session: AsyncSession, stage_id: Any) -> str | None:
    stage = await _get(session, Stage, stage_id)
    return stage.name if stage is not None else None


async def _user_names(session: AsyncSession, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    linhas = (await session.execute(select(User.id, User.name).where(User.id.in_(user_ids)))).all()
    return {row[0]: row[1] for row in linhas}


async def _get(session: AsyncSession, model: Any, raw_id: Any) -> Any:
    if raw_id is None:
        return None
    try:
        return await session.get(model, uuid.UUID(str(raw_id)))
    except (ValueError, AttributeError):  # pragma: no cover - id malformado no payload
        return None


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None

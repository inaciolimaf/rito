"""As ações que uma automação sabe executar (spec 092 §2).

Cada ação passa pelo **service do domínio**, nunca escrevendo direto na tabela: a mesma
validação que reprova um humano reprova a automação. É a regra 5 da 084 aplicada aqui —
automação é mais um cliente do domínio, não um atalho por dentro dele.

Regra 12: o ator é sempre quem CRIOU a automação. Se fosse quem disparou o evento, a
mesma regra faria coisas diferentes conforme quem mexeu no processo — e um Colaborador
concluindo uma tarefa acabaria movendo etapas que ele não pode mover.
"""

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from app.domain.automations.conditions import evaluate
from app.domain.automations.models import (
    ActionKind,
    Automation,
    AutomationAction,
    AutomationRun,
)
from app.domain.lawsuits.models import Lawsuit
from app.domain.users.models import User

if TYPE_CHECKING:  # pragma: no cover
    from app.domain.automations.engine import AutomationEngine


class ConditionNotMet(Exception):
    """`wait_condition` cuja condição ainda não é verdade — a execução ESPERA.

    Não é erro: a automação "quando o processo estiver arquivado, notifique" pode ficar
    meses aqui, e isso é exatamente o comportamento pedido.
    """


class UnknownActionError(Exception):
    pass


async def run_action(
    engine: "AutomationEngine",
    *,
    run: AutomationRun,
    action: AutomationAction,
    automation: Automation,
    actor: User,
) -> dict[str, Any]:
    config = dict(action.action_config or {})
    if action.action_kind == ActionKind.WAIT_CONDITION.value:
        if not evaluate(config.get("condition"), run.trigger_payload or {}):
            raise ConditionNotMet
        return {"waited": False}
    if action.action_kind == ActionKind.CREATE_TASK.value:
        return await _create_task(engine, run=run, config=config, actor=actor)
    if action.action_kind == ActionKind.SET_ASSIGNEE.value:
        return await _set_assignee(engine, run=run, config=config)
    if action.action_kind == ActionKind.CHANGE_STAGE.value:
        return await _change_stage(engine, run=run, config=config, actor=actor)
    if action.action_kind == ActionKind.NOTIFY.value:
        return await _notify(engine, run=run, config=config)
    raise UnknownActionError(f"Ação desconhecida: {action.action_kind}")


async def _lawsuit_of(engine: "AutomationEngine", run: AutomationRun) -> Lawsuit:
    lawsuit_id = (run.trigger_payload or {}).get("lawsuit_id")
    if lawsuit_id is None:
        raise ValueError("Esta ação exige um processo, e o gatilho não trouxe nenhum.")
    lawsuit = await engine.session.get(Lawsuit, uuid.UUID(str(lawsuit_id)))
    if lawsuit is None:
        raise ValueError("O processo do gatilho não existe mais.")
    return lawsuit


async def _create_task(
    engine: "AutomationEngine", *, run: AutomationRun, config: dict[str, Any], actor: User
) -> dict[str, Any]:
    from app.domain.posts.creation import CreatePostUseCase
    from app.domain.posts.exceptions import DuplicatePostError
    from app.domain.posts.schemas import PostCreateRequest

    lawsuit = await _lawsuit_of(engine, run)
    prazo_em = config.get("deadline_days")
    deadline = None
    if prazo_em is not None:
        from app.core.dates import add_business_days

        deadline = add_business_days(engine.now().date(), int(prazo_em), await engine._holidays())
    responsaveis = [uuid.UUID(str(item)) for item in config.get("user_ids", [])] or [
        lawsuit.user_id
    ]
    payload = PostCreateRequest(
        lawsuit_id=lawsuit.id,
        task_type_id=uuid.UUID(str(config["task_type_id"])),
        scheduled_date=deadline or engine.now().date(),
        deadline_date=deadline,
        comments=config.get("comments"),
        user_ids=responsaveis,
    )
    use_case = CreatePostUseCase(engine.session, engine.tenant_id)
    try:
        criada = await use_case.create(payload, actor)
    except DuplicatePostError as exc:
        # A automação rodando duas vezes sobre o mesmo processo não pode criar a tarefa
        # duas vezes — e o domínio já sabe reconhecer a duplicata (spec 032).
        return {"created_post_id": str(exc.existing_id), "duplicate": True}
    return {"created_post_id": str(criada.post.id), "task_type_id": str(payload.task_type_id)}


async def _set_assignee(
    engine: "AutomationEngine", *, run: AutomationRun, config: dict[str, Any]
) -> dict[str, Any]:
    lawsuit = await _lawsuit_of(engine, run)
    novo = uuid.UUID(str(config["user_id"]))
    anterior = lawsuit.user_id
    lawsuit.user_id = novo
    await engine.session.flush()
    return {"lawsuit_id": str(lawsuit.id), "from": str(anterior), "to": str(novo)}


async def _change_stage(
    engine: "AutomationEngine", *, run: AutomationRun, config: dict[str, Any], actor: User
) -> dict[str, Any]:
    from app.domain.lawsuits.board_service import BoardService

    lawsuit = await _lawsuit_of(engine, run)
    destino = uuid.UUID(str(config["stage_id"]))
    service = BoardService(engine.session, engine.tenant_id)
    # Pelo `change_stage`, não atribuindo `stage_id`: é o único caminho que grava o
    # histórico de etapa (spec 052).
    await service.change_stage(lawsuit, to_stage_id=destino, changed_by=actor.id)
    return {"lawsuit_id": str(lawsuit.id), "stage_id": str(destino)}


async def _notify(
    engine: "AutomationEngine", *, run: AutomationRun, config: dict[str, Any]
) -> dict[str, Any]:
    from app.domain.notifications.service import NotificationService

    destino = config.get("user_id")
    if destino is None:
        destino = (await _lawsuit_of(engine, run)).user_id
    service = NotificationService(engine.session, engine.tenant_id)
    await service.notify(
        user_id=uuid.UUID(str(destino)),
        kind="automation",
        title=str(config.get("title", "Automação")),
        body=config.get("body"),
        link=config.get("link"),
    )
    return {"notified": str(destino)}


CONDITION_RETRY = timedelta(hours=1)


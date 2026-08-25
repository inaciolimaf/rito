"""Ferramentas de escrita (spec 084).

A regra que carrega a spec inteira está no tipo: uma `WriteToolDef` tem `preview` e
`execute` **separados**, e o runner só sabe chamar o primeiro. Executar é privilégio do
`AiActionService`, depois de um humano aprovar — não existe caminho em que uma chamada
de ferramenta grave algo direto (regra 1).

Não há ferramenta de exclusão, e não vai haver (regra 13): há teste meta que reprova
qualquer nome com cara de apagar.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import ToolContext, ToolError
from app.core.permissions import FinancialAccess, UserRole

# ------------------------------------------------------------------ contrato


@dataclass(frozen=True)
class Proposal:
    """O que a ferramenta propõe. Vira `ai_actions.preview` e o `AIActionPreview` da UI."""

    affected_type: str
    summary: str
    # `changes` é campo a campo: {campo: {"before": ..., "after": ...}} na atualização,
    # {campo: {"after": ...}} na criação — é o que a UI pinta de verde e amarelo.
    changes: dict[str, dict[str, Any]]
    affected_id: uuid.UUID | None = None
    before_state: dict[str, Any] | None = None

    def to_preview(self) -> dict[str, Any]:
        return {
            "affected_type": self.affected_type,
            "affected_id": str(self.affected_id) if self.affected_id else None,
            "summary": self.summary,
            # O preview vai para JSONB e para a UI: data e UUID viram texto aqui, uma
            # vez, em vez de em cada ferramenta.
            "changes": {
                field: {key: _plain(value) for key, value in change.items()}
                for field, change in self.changes.items()
            },
        }


@dataclass(frozen=True)
class Executed:
    affected_id: uuid.UUID
    after_state: dict[str, Any]


PreviewFn = Callable[[ToolContext, Any], Awaitable[Proposal]]
ExecuteFn = Callable[[ToolContext, Any], Awaitable[Executed]]


@dataclass(frozen=True)
class WriteToolDef:
    name: str
    description: str
    params_model: type[BaseModel]
    preview: PreviewFn
    execute: ExecuteFn
    requires_role: UserRole = UserRole.COLABORADOR
    requires_financial: FinancialAccess = FinancialAccess.NONE

    def json_schema(self) -> dict[str, Any]:
        schema = self.params_model.model_json_schema()
        schema.pop("title", None)
        return schema


_WRITE_REGISTRY: dict[str, WriteToolDef] = {}


def register_write_tool(definition: WriteToolDef) -> WriteToolDef:
    _WRITE_REGISTRY[definition.name] = definition
    return definition


def get_write_tool(name: str) -> WriteToolDef | None:
    from app.ai.tools.loader import ensure_tools_loaded

    ensure_tools_loaded()
    return _WRITE_REGISTRY.get(name)


def all_write_tools() -> list[WriteToolDef]:
    from app.ai.tools.loader import ensure_tools_loaded

    ensure_tools_loaded()
    return [_WRITE_REGISTRY[name] for name in sorted(_WRITE_REGISTRY)]


def _informados(params: BaseModel, *, exclude: set[str]) -> dict[str, Any]:
    """Só os campos que quem chamou informou de verdade — inclusive os informados como
    nulo, que são o caminho do desfazer (spec 084, regra 10)."""
    return {
        field: getattr(params, field) for field in params.model_fields_set if field not in exclude
    }


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID | date):
        return str(value)
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Regra 2: só o que MUDA entra no preview — listar campo intocado esconde a
    mudança real no meio do ruído."""
    changes: dict[str, dict[str, Any]] = {}
    for field, value in after.items():
        if value is None:
            continue
        anterior = before.get(field)
        if anterior != value:
            changes[field] = {"before": anterior, "after": value}
    return changes


def _created(fields: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {key: {"after": value} for key, value in fields.items() if value is not None}


# ------------------------------------------------------------------ contatos


class CreateCustomerInput(BaseModel):
    name: str = Field(min_length=2)
    # Origem é obrigatória no cadastro de contato (spec 017) — a IA não escapa disso
    # (regra 5). Use `list_taxonomies` para descobrir o id.
    origin_id: uuid.UUID = Field(description="Origem do contato; veja list_taxonomies.")
    type: str = Field(default="PF", description="PF | PJ")
    identification: str | None = Field(default=None, description="CPF ou CNPJ, só dígitos.")
    email: str | None = None
    cellphone: str | None = None
    city: str | None = None
    state: str | None = None


class UpdateCustomerInput(BaseModel):
    customer_id: uuid.UUID
    name: str | None = None
    email: str | None = None
    cellphone: str | None = None
    city: str | None = None
    state: str | None = None
    notes: str | None = None


async def _preview_create_customer(ctx: ToolContext, params: CreateCustomerInput) -> Proposal:
    return Proposal(
        affected_type="customer",
        summary=f"Criar o contato {params.name}",
        changes=_created(params.model_dump(exclude_none=True)),
    )


async def _execute_create_customer(ctx: ToolContext, params: CreateCustomerInput) -> Executed:
    from app.domain.customers.schemas import CustomerCreateRequest
    from app.domain.customers.service import CustomerService

    service = CustomerService(session=ctx.session, tenant_id=ctx.tenant_id)
    # Regra 5: a IA passa pelo MESMO service do humano — validação que reprova um
    # reprova o outro.
    created = await service.create(
        CustomerCreateRequest.model_validate(params.model_dump(exclude_none=True))
    )
    return Executed(
        affected_id=created.id,
        after_state={"id": str(created.id), "name": created.name, "type": created.type.value},
    )


async def _preview_update_customer(ctx: ToolContext, params: UpdateCustomerInput) -> Proposal:
    from app.domain.customers.service import CustomerService

    service = CustomerService(session=ctx.session, tenant_id=ctx.tenant_id)
    customer = await service.get(params.customer_id)
    if customer is None:
        raise ToolError("not_found", "Contato não encontrado neste escritório.")
    before = {
        "name": customer.name,
        "email": customer.email,
        "cellphone": customer.cellphone,
        "city": customer.city,
        "state": customer.state,
        "notes": customer.notes,
    }
    after = params.model_dump(exclude={"customer_id"}, exclude_none=True)
    changes = _diff(before, after)
    if not changes:
        raise ToolError("no_changes", "Nada mudaria neste contato — não proponha a alteração.")
    return Proposal(
        affected_type="customer",
        affected_id=customer.id,
        summary=f"Atualizar o contato {customer.name}",
        changes=changes,
        before_state=before,
    )


async def _execute_update_customer(ctx: ToolContext, params: UpdateCustomerInput) -> Executed:
    from app.domain.customers.schemas import CustomerUpdateRequest
    from app.domain.customers.service import CustomerService

    service = CustomerService(session=ctx.session, tenant_id=ctx.tenant_id)
    customer = await service.get(params.customer_id)
    if customer is None:
        raise ToolError("not_found", "Contato não encontrado neste escritório.")
    # O contrato de atualização do domínio é o cadastro inteiro (PUT), então o payload
    # parte do estado ATUAL e só sobrescreve o que a proposta mudou — mandar só os
    # campos alterados apagaria o resto.
    payload = {
        "type": customer.type.value,
        "name": customer.name,
        "origin_id": customer.origin_id,
        "identification": customer.identification,
        "email": customer.email,
        "cellphone": customer.cellphone,
        "city": customer.city,
        "state": customer.state,
        "notes": customer.notes,
        # `model_fields_set` em vez de `exclude_none`: desfazer (regra 10) precisa
        # conseguir devolver um campo para NULL, e "não informado" é diferente de
        # "informado como vazio".
        **_informados(params, exclude={"customer_id"}),
    }
    updated = await service.update(customer, CustomerUpdateRequest.model_validate(payload))
    return Executed(
        affected_id=updated.id,
        after_state={
            "id": str(updated.id),
            "name": updated.name,
            "email": updated.email,
            "cellphone": updated.cellphone,
            "city": updated.city,
            "state": updated.state,
            "notes": updated.notes,
        },
    )


# ------------------------------------------------------------------ processos


class CreateLawsuitInput(BaseModel):
    customer_id: uuid.UUID = Field(description="Cliente no polo ativo.")
    lawsuit_type_id: uuid.UUID
    stage_id: uuid.UUID
    responsible_id: uuid.UUID
    folder: str | None = None
    process_number: str | None = None
    notes: str | None = None


class UpdateLawsuitInput(BaseModel):
    lawsuit_id: uuid.UUID
    folder: str | None = None
    notes: str | None = None
    county: str | None = None


class MoveStageInput(BaseModel):
    lawsuit_id: uuid.UUID
    stage_id: uuid.UUID


async def _preview_create_lawsuit(ctx: ToolContext, params: CreateLawsuitInput) -> Proposal:
    return Proposal(
        affected_type="lawsuit",
        summary="Abrir um processo",
        changes=_created(params.model_dump(exclude_none=True)),
    )


async def _execute_create_lawsuit(ctx: ToolContext, params: CreateLawsuitInput) -> Executed:
    from app.domain.lawsuits.schemas import LawsuitCreateRequest
    from app.domain.lawsuits.service import LawsuitService

    service = LawsuitService(session=ctx.session, tenant_id=ctx.tenant_id)
    detail = await service.create(
        LawsuitCreateRequest.model_validate(
            {
                "user_id": params.responsible_id,
                "lawsuit_type_id": params.lawsuit_type_id,
                "stage_id": params.stage_id,
                "folder": params.folder,
                "process_number": params.process_number,
                "notes": params.notes,
                "parties": [
                    {"customer_id": params.customer_id, "pole": "ATIVO", "is_client": True}
                ],
            }
        )
    )
    return Executed(
        affected_id=detail.lawsuit.id,
        after_state={
            "id": str(detail.lawsuit.id),
            "folder": detail.lawsuit.folder,
            "process_number": detail.lawsuit.process_number,
            "stage_id": str(detail.lawsuit.stage_id),
        },
    )


async def _load_lawsuit(ctx: ToolContext, lawsuit_id: uuid.UUID) -> Any:
    from app.domain.lawsuits.repository import LawsuitRepository

    lawsuit = await LawsuitRepository(ctx.session).get_by_id(lawsuit_id)
    if lawsuit is None:
        raise ToolError("not_found", "Processo não encontrado neste escritório.")
    return lawsuit


async def _preview_update_lawsuit(ctx: ToolContext, params: UpdateLawsuitInput) -> Proposal:
    lawsuit = await _load_lawsuit(ctx, params.lawsuit_id)
    before = {"folder": lawsuit.folder, "notes": lawsuit.notes, "county": lawsuit.county}
    changes = _diff(before, params.model_dump(exclude={"lawsuit_id"}, exclude_none=True))
    if not changes:
        raise ToolError("no_changes", "Nada mudaria neste processo — não proponha a alteração.")
    return Proposal(
        affected_type="lawsuit",
        affected_id=lawsuit.id,
        summary=f"Atualizar o processo {lawsuit.process_number or lawsuit.folder or ''}".strip(),
        changes=changes,
        before_state=before,
    )


async def _execute_update_lawsuit(ctx: ToolContext, params: UpdateLawsuitInput) -> Executed:
    from app.domain.lawsuits.schemas import LawsuitUpdateRequest
    from app.domain.lawsuits.service import LawsuitService

    lawsuit = await _load_lawsuit(ctx, params.lawsuit_id)
    service = LawsuitService(session=ctx.session, tenant_id=ctx.tenant_id)
    payload = LawsuitUpdateRequest.model_validate(
        {
            "user_id": lawsuit.user_id,
            "lawsuit_type_id": lawsuit.lawsuit_type_id,
            "stage_id": lawsuit.stage_id,
            "folder": lawsuit.folder,
            "notes": lawsuit.notes,
            "county": lawsuit.county,
            "process_number": lawsuit.process_number,
            **_informados(params, exclude={"lawsuit_id"}),
        }
    )
    detail = await service.update(lawsuit, payload, changed_by=ctx.user.id)
    return Executed(
        affected_id=detail.lawsuit.id,
        after_state={
            "id": str(detail.lawsuit.id),
            "folder": detail.lawsuit.folder,
            "notes": detail.lawsuit.notes,
            "county": detail.lawsuit.county,
        },
    )


async def _preview_move_stage(ctx: ToolContext, params: MoveStageInput) -> Proposal:
    from app.domain.stages.repository import StageRepository

    lawsuit = await _load_lawsuit(ctx, params.lawsuit_id)
    stages = StageRepository(ctx.session)
    destino = await stages.get_by_id(params.stage_id)
    if destino is None:
        raise ToolError("not_found", "Etapa não encontrada neste escritório.")
    origem = await stages.get_by_id(lawsuit.stage_id)
    if lawsuit.stage_id == params.stage_id:
        raise ToolError("no_changes", "O processo já está nessa etapa.")
    return Proposal(
        affected_type="lawsuit",
        affected_id=lawsuit.id,
        summary=f"Mover o processo para a etapa {destino.name}",
        changes={
            "stage": {
                "before": origem.name if origem else None,
                "after": destino.name,
            }
        },
        before_state={"stage_id": str(lawsuit.stage_id)},
    )


async def _execute_move_stage(ctx: ToolContext, params: MoveStageInput) -> Executed:
    from app.domain.lawsuits.board_service import BoardService

    lawsuit = await _load_lawsuit(ctx, params.lawsuit_id)
    service = BoardService(session=ctx.session, tenant_id=ctx.tenant_id)
    moved = await service.move_stage(lawsuit, stage_id=params.stage_id, actor=ctx.user)
    return Executed(
        affected_id=moved.id, after_state={"id": str(moved.id), "stage_id": str(moved.stage_id)}
    )


# ------------------------------------------------------------------ tarefas


class CreateTaskInput(BaseModel):
    lawsuit_id: uuid.UUID
    task_type_id: uuid.UUID
    assignee_ids: list[uuid.UUID] = Field(min_length=1)
    scheduled_date: date | None = None
    deadline_date: date | None = None
    comments: str | None = None
    is_urgent: bool = False


class CompleteTaskInput(BaseModel):
    post_id: uuid.UUID
    comment: str | None = None


async def _preview_create_task(ctx: ToolContext, params: CreateTaskInput) -> Proposal:
    from app.domain.task_types.repository import TaskTypeRepository

    task_type = await TaskTypeRepository(ctx.session).get_by_id(params.task_type_id)
    if task_type is None:
        raise ToolError("not_found", "Tipo de tarefa não encontrado neste escritório.")
    await _load_lawsuit(ctx, params.lawsuit_id)
    fields = params.model_dump(exclude_none=True)
    fields["task_type"] = task_type.name
    fields["assignee_ids"] = [str(item) for item in params.assignee_ids]
    return Proposal(
        affected_type="post",
        summary=f"Criar a tarefa {task_type.name}",
        changes=_created(fields),
    )


async def _execute_create_task(ctx: ToolContext, params: CreateTaskInput) -> Executed:
    from app.domain.posts.creation import CreatePostUseCase
    from app.domain.posts.schemas import PostCreateRequest

    use_case = CreatePostUseCase(session=ctx.session, tenant_id=ctx.tenant_id)
    detail = await use_case.create(
        PostCreateRequest.model_validate(
            {
                "lawsuit_id": params.lawsuit_id,
                "task_type_id": params.task_type_id,
                "user_ids": params.assignee_ids,
                "scheduled_date": params.scheduled_date,
                "deadline_date": params.deadline_date,
                "comments": params.comments,
                "is_urgent": params.is_urgent,
            }
        ),
        ctx.user,
    )
    return Executed(
        affected_id=detail.post.id,
        after_state={"id": str(detail.post.id), "task_type": detail.task_type_name},
    )


async def _preview_complete_task(ctx: ToolContext, params: CompleteTaskInput) -> Proposal:
    from app.domain.posts.service import PostService

    service = PostService(session=ctx.session, tenant_id=ctx.tenant_id)
    detail = await service.get(params.post_id, viewer_id=ctx.user.id)
    if detail is None:
        raise ToolError("not_found", "Tarefa não encontrada (ou é privada de outra pessoa).")
    return Proposal(
        affected_type="post",
        affected_id=detail.post.id,
        summary=f"Concluir a tarefa {detail.task_type_name}",
        changes={"completed": {"before": False, "after": True}},
        before_state={"completed": False},
    )


async def _execute_complete_task(ctx: ToolContext, params: CompleteTaskInput) -> Executed:
    from app.domain.posts.completion import CompletePostUseCase
    from app.domain.posts.repository import PostRepository
    from app.domain.posts.schemas import PostCompleteRequest

    post = await PostRepository(ctx.session).get_by_id(params.post_id)
    if post is None:
        raise ToolError("not_found", "Tarefa não encontrada neste escritório.")
    use_case = CompletePostUseCase(session=ctx.session, tenant_id=ctx.tenant_id)
    detail = await use_case.complete(
        post, ctx.user, PostCompleteRequest.model_validate({"comment": params.comment})
    )
    return Executed(
        affected_id=detail.post.id,
        after_state={"id": str(detail.post.id), "completed": True},
    )


# ------------------------------------------------------------------ financeiro


class CreateTransactionInput(BaseModel):
    kind: str = Field(description="RECEITA | DESPESA")
    amount: str = Field(description="Valor com ponto decimal, ex.: '1500.00'.")
    due_date: date
    category_id: uuid.UUID
    cost_center_id: uuid.UUID
    debit_account_id: uuid.UUID
    description: str | None = None


async def _preview_create_transaction(ctx: ToolContext, params: CreateTransactionInput) -> Proposal:
    return Proposal(
        affected_type="transaction",
        summary=f"Lançar {params.kind.lower()} de R$ {params.amount}",
        changes=_created(params.model_dump(exclude_none=True)),
    )


async def _execute_create_transaction(ctx: ToolContext, params: CreateTransactionInput) -> Executed:
    from app.domain.financial.schemas import TransactionCreateRequest
    from app.domain.financial.service import TransactionService

    service = TransactionService(session=ctx.session, tenant_id=ctx.tenant_id)
    row = await service.create(
        TransactionCreateRequest.model_validate(params.model_dump(exclude_none=True)), ctx.user
    )
    return Executed(
        affected_id=row.transaction.id,
        after_state={
            "id": str(row.transaction.id),
            "kind": row.transaction.kind.value,
            "amount": str(row.transaction.amount),
        },
    )


# ------------------------------------------------------- intimações e workflows


class LinkPublicationInput(BaseModel):
    publication_id: uuid.UUID
    lawsuit_id: uuid.UUID


class ApplyWorkflowInput(BaseModel):
    lawsuit_id: uuid.UUID
    workflow_id: uuid.UUID


async def _preview_link_publication(ctx: ToolContext, params: LinkPublicationInput) -> Proposal:
    from app.domain.publications.service import PublicationService

    service = PublicationService(session=ctx.session, tenant_id=ctx.tenant_id)
    publication = await service.get_by_id(params.publication_id)
    if publication is None:
        raise ToolError("not_found", "Intimação não encontrada neste escritório.")
    lawsuit = await _load_lawsuit(ctx, params.lawsuit_id)
    return Proposal(
        affected_type="publication",
        affected_id=publication.id,
        summary="Vincular a intimação ao processo",
        changes={
            "lawsuit_id": {
                "before": str(publication.lawsuit_id) if publication.lawsuit_id else None,
                "after": str(lawsuit.id),
            }
        },
        before_state={
            "lawsuit_id": str(publication.lawsuit_id) if publication.lawsuit_id else None
        },
    )


async def _execute_link_publication(ctx: ToolContext, params: LinkPublicationInput) -> Executed:
    from app.domain.publications.routing import PublicationRoutingService
    from app.domain.publications.service import PublicationService

    service = PublicationService(session=ctx.session, tenant_id=ctx.tenant_id)
    publication = await service.get_by_id(params.publication_id)
    if publication is None:
        raise ToolError("not_found", "Intimação não encontrada neste escritório.")
    routing = PublicationRoutingService(session=ctx.session, tenant_id=ctx.tenant_id)
    linked = await routing.link(publication, params.lawsuit_id)
    return Executed(
        affected_id=linked.id,
        after_state={"id": str(linked.id), "lawsuit_id": str(linked.lawsuit_id)},
    )


async def _preview_apply_workflow(ctx: ToolContext, params: ApplyWorkflowInput) -> Proposal:
    from app.domain.workflows.repository import WorkflowRepository

    lawsuit = await _load_lawsuit(ctx, params.lawsuit_id)
    workflow = await WorkflowRepository(ctx.session).get_by_id(params.workflow_id)
    if workflow is None:
        raise ToolError("not_found", "Workflow não encontrado neste escritório.")
    return Proposal(
        affected_type="lawsuit",
        affected_id=lawsuit.id,
        summary=f"Aplicar o workflow {workflow.name} ao processo",
        changes={"workflow": {"after": workflow.name}},
    )


async def _execute_apply_workflow(ctx: ToolContext, params: ApplyWorkflowInput) -> Executed:
    from app.domain.lawsuits.workflow_service import LawsuitWorkflowService
    from app.domain.workflows.repository import WorkflowRepository

    lawsuit = await _load_lawsuit(ctx, params.lawsuit_id)
    workflow = await WorkflowRepository(ctx.session).get_by_id(params.workflow_id)
    if workflow is None:
        raise ToolError("not_found", "Workflow não encontrado neste escritório.")
    service = LawsuitWorkflowService(session=ctx.session, tenant_id=ctx.tenant_id)
    outcome = await service.apply(
        lawsuit, workflow, ctx.user, stage_id=None, confirm_duplicate=True
    )
    return Executed(
        affected_id=lawsuit.id,
        after_state={
            "id": str(lawsuit.id),
            "workflow": workflow.name,
            "application_id": str(outcome.application.id),
            "skipped": len(outcome.skipped),
        },
    )


_DEFINITIONS = [
    WriteToolDef(
        name="create_customer",
        description="Propõe criar um contato (cliente, parte ou terceiro). Exige confirmação.",
        params_model=CreateCustomerInput,
        preview=_preview_create_customer,
        execute=_execute_create_customer,
    ),
    WriteToolDef(
        name="update_customer",
        description="Propõe atualizar dados de um contato existente. Exige confirmação.",
        params_model=UpdateCustomerInput,
        preview=_preview_update_customer,
        execute=_execute_update_customer,
    ),
    WriteToolDef(
        name="create_lawsuit",
        description="Propõe abrir um processo para um cliente. Exige confirmação.",
        params_model=CreateLawsuitInput,
        preview=_preview_create_lawsuit,
        execute=_execute_create_lawsuit,
    ),
    WriteToolDef(
        name="update_lawsuit",
        description="Propõe atualizar pasta, comarca ou observações de um processo.",
        params_model=UpdateLawsuitInput,
        preview=_preview_update_lawsuit,
        execute=_execute_update_lawsuit,
    ),
    WriteToolDef(
        name="move_lawsuit_stage",
        description="Propõe mover um processo para outra etapa do fluxo. Exige confirmação.",
        params_model=MoveStageInput,
        preview=_preview_move_stage,
        execute=_execute_move_stage,
    ),
    WriteToolDef(
        name="create_task",
        description="Propõe criar uma tarefa num processo, com responsáveis e prazo.",
        params_model=CreateTaskInput,
        preview=_preview_create_task,
        execute=_execute_create_task,
    ),
    WriteToolDef(
        name="complete_task",
        description="Propõe concluir uma tarefa em nome do usuário. Exige confirmação.",
        params_model=CompleteTaskInput,
        preview=_preview_complete_task,
        execute=_execute_complete_task,
    ),
    WriteToolDef(
        name="create_transaction",
        description="Propõe um lançamento financeiro (receita ou despesa).",
        params_model=CreateTransactionInput,
        preview=_preview_create_transaction,
        execute=_execute_create_transaction,
        requires_financial=FinancialAccess.FULL,
    ),
    WriteToolDef(
        name="link_publication",
        description="Propõe vincular uma intimação recebida a um processo.",
        params_model=LinkPublicationInput,
        preview=_preview_link_publication,
        execute=_execute_link_publication,
    ),
    WriteToolDef(
        name="apply_workflow",
        description="Propõe aplicar um workflow a um processo, criando as tarefas dele.",
        params_model=ApplyWorkflowInput,
        preview=_preview_apply_workflow,
        execute=_execute_apply_workflow,
        requires_role=UserRole.ADMINISTRADOR,
    ),
]

for _definition in _DEFINITIONS:
    register_write_tool(_definition)

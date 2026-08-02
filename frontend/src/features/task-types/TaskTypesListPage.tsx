import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import { TransferBeforeDeleteDialog } from "@/components/domain/TransferBeforeDeleteDialog";
import type { DataTableColumn, EntityOption, FilterFieldDef } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useFilters } from "@/components/domain/useFilters";
import { Button } from "@/components/ui/button";
import { listSteps } from "@/features/stages/api";
import {
  createTaskType,
  deleteTaskType,
  listTaskTypes,
  transferTaskTypes,
  updateTaskType,
  type TaskTypeData,
  type TaskTypePayload,
} from "@/features/task-types/api";
import {
  DEFAULT_TASK_TYPE_FORM_VALUES,
  taskTypeFormSchema,
  type TaskTypeFormValues,
} from "@/features/task-types/schema";
import { TaskTypeForm } from "@/features/task-types/TaskTypeForm";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

function toPayload(values: TaskTypeFormValues): TaskTypePayload {
  return {
    name: values.name,
    step_id: values.step_id ? Number(values.step_id) : null,
    complexity: (values.complexity || null) as TaskTypePayload["complexity"],
    duration: (values.duration || null) as TaskTypePayload["duration"],
    reward: values.reward === "" ? null : Number(values.reward),
    show_in_schedule: values.show_in_schedule,
  };
}

function toFormValues(taskType: TaskTypeData): TaskTypeFormValues {
  return {
    name: taskType.name,
    step_id: taskType.step_id != null ? String(taskType.step_id) : "",
    complexity: taskType.complexity ?? "",
    duration: taskType.duration ?? "",
    reward: String(taskType.reward),
    show_in_schedule: taskType.show_in_schedule,
  };
}

/** Configurações > Tarefas (spec 031): catálogo com Taskscore. Só GESTOR escreve
 * (regra 1) — os demais perfis veem a listagem sem ações. */
export function TaskTypesListPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";
  const queryClient = useQueryClient();

  const { data: steps = [] } = useQuery({ queryKey: ["steps"], queryFn: listSteps });

  const filterFields: FilterFieldDef[] = [
    { key: "q", label: "Buscar", type: "text" },
    {
      key: "step_id",
      label: "Fase",
      type: "select",
      options: steps.map((step) => ({ value: String(step.id), label: step.name })),
    },
    {
      key: "status",
      label: "Status",
      type: "select",
      options: [
        { value: "active", label: "Ativo" },
        { value: "inactive", label: "Inativo" },
      ],
    },
  ];

  const { values } = useFilters(filterFields);
  const q = typeof values.q === "string" ? values.q : undefined;
  const stepId = typeof values.step_id === "string" ? Number(values.step_id) : undefined;
  const status =
    typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined;

  const [transferDialogOpen, setTransferDialogOpen] = React.useState(false);
  const [transferError, setTransferError] = React.useState<ApiError | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["task-types", { q, stepId, status }],
    queryFn: () => listTaskTypes({ q, step_id: stepId, status }),
  });
  const taskTypes = data?.items ?? [];

  const {
    editing: editingTaskType,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
  } = useCrudResource<TaskTypeData, TaskTypeFormValues>({
    queryKey: ["task-types"],
    create: (values) => createTaskType(toPayload(values)),
    update: (taskType, values) =>
      updateTaskType(taskType.id, { ...toPayload(values), is_active: taskType.is_active }),
    remove: (taskType) => deleteTaskType(taskType.id),
  });

  function requestDelete(taskType: TaskTypeData): void {
    setTransferError(null);
    setPendingDelete(taskType);
  }

  async function handleConfirmDeleteWithTransfer(): Promise<void> {
    if (!pendingDelete) return;
    // Regra 5: em uso (409) abre a transferência — possível só a partir da spec 032;
    // sem tarefas, o delete direto sempre passa.
    try {
      await deleteTaskType(pendingDelete.id);
      setPendingDelete(null);
      await queryClient.invalidateQueries({ queryKey: ["task-types"] });
    } catch (deleteError) {
      if (deleteError instanceof ApiError && deleteError.status === 409) {
        setTransferDialogOpen(true);
      } else {
        setPendingDelete(null);
        setTransferError(deleteError instanceof ApiError ? deleteError : null);
      }
    }
  }

  async function handleTransferAndDelete(destinationId: string): Promise<void> {
    if (!pendingDelete) return;
    try {
      await transferTaskTypes(pendingDelete.id, destinationId);
      await deleteTaskType(pendingDelete.id);
      setPendingDelete(null);
      await queryClient.invalidateQueries({ queryKey: ["task-types"] });
    } catch (submitError) {
      setTransferError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  const transferOptions: EntityOption[] = taskTypes
    .filter((taskType) => taskType.id !== pendingDelete?.id && !taskType.is_system)
    .map((taskType) => ({ id: taskType.id, label: taskType.name }));

  const columns: DataTableColumn<TaskTypeData>[] = [
    { id: "name", header: "Tarefa", cell: (row) => row.name },
    { id: "reward", header: "Pontuação", cell: (row) => row.reward },
    {
      id: "last_assigned_at",
      header: "Última atribuição",
      // Regra 9: derivada — tarefas só existem na spec 032.
      cell: (row) =>
        row.last_assigned_at ? new Date(row.last_assigned_at).toLocaleDateString("pt-BR") : "—",
    },
    { id: "step", header: "Fase", cell: (row) => row.step_name ?? "Todas" },
    {
      id: "created_at",
      header: "Cadastro",
      cell: (row) => new Date(row.created_at).toLocaleDateString("pt-BR"),
    },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Tarefas</h1>
        {isGestor && <Button onClick={openCreateModal}>Nova tarefa</Button>}
      </div>

      <FilterBar fields={filterFields} />

      <DataTable
        columns={columns}
        data={taskTypes}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum tipo de tarefa encontrado."
        rowActions={
          isGestor
            ? (row) => (
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-sm text-accent underline"
                    onClick={() => openEditModal(row)}
                  >
                    Editar
                  </button>
                  {!row.is_system && (
                    <button
                      type="button"
                      className="text-sm text-danger underline"
                      onClick={() => requestDelete(row)}
                    >
                      Excluir
                    </button>
                  )}
                </div>
              )
            : undefined
        }
      />

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingTaskType ? "Editar tarefa" : "Nova tarefa"}
        schema={taskTypeFormSchema}
        defaultValues={
          editingTaskType ? toFormValues(editingTaskType) : DEFAULT_TASK_TYPE_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => <TaskTypeForm form={form} isSystem={editingTaskType?.is_system ?? false} />}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null && !transferDialogOpen}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir tipo de tarefa?"
        description={`"${pendingDelete?.name ?? ""}" será excluído do catálogo.`}
        confirmLabel="Excluir"
        destructive
        onConfirm={() => void handleConfirmDeleteWithTransfer()}
      />

      <TransferBeforeDeleteDialog
        open={transferDialogOpen && pendingDelete !== null}
        onOpenChange={(open) => {
          setTransferDialogOpen(open);
          if (!open) setPendingDelete(null);
        }}
        title="Transferir tarefas antes de excluir"
        description={`"${pendingDelete?.name ?? ""}" está em uso (regra 5). Escolha o tipo de destino — as tarefas migram para lá antes da exclusão.`}
        options={transferOptions}
        onTransfer={handleTransferAndDelete}
      />
      {transferError && (
        <p role="alert" className="text-sm text-danger">
          {transferError.message}
        </p>
      )}
    </div>
  );
}

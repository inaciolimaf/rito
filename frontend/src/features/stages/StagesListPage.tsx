import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import {
  createStage,
  deleteStage,
  listStages,
  listSteps,
  reorderStages,
  updateStage,
  type StageData,
} from "@/features/stages/api";
import { StageForm } from "@/features/stages/StageForm";
import { StageReorderList } from "@/features/stages/StageReorderList";
import {
  DEFAULT_STAGE_FORM_VALUES,
  stageFormSchema,
  type StageFormValues,
} from "@/features/stages/schema";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

export function StagesListPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";
  const queryClient = useQueryClient();

  const { data: steps = [] } = useQuery({ queryKey: ["steps"], queryFn: listSteps });

  const filterFields: FilterFieldDef[] = [
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
    { key: "q", label: "Buscar", type: "text" },
  ];

  const { values } = useFilters(filterFields);
  const stepId =
    typeof values.step_id === "string" && values.step_id ? Number(values.step_id) : undefined;
  const status =
    typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined;
  const q = typeof values.q === "string" ? values.q : undefined;

  const [reorderMode, setReorderMode] = React.useState(false);
  const [editingStage, setEditingStage] = React.useState<StageData | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);
  const [formError, setFormError] = React.useState<ApiError | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<StageData | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["stages", { stepId, status, q }],
    queryFn: () => listStages({ step_id: stepId, status, q }),
  });
  const stages = data?.items ?? [];

  function openCreateModal(): void {
    setEditingStage(null);
    setFormError(null);
    setModalOpen(true);
  }

  function openEditModal(stage: StageData): void {
    setEditingStage(stage);
    setFormError(null);
    setModalOpen(true);
  }

  async function handleSubmit(values: StageFormValues): Promise<void> {
    setFormError(null);
    const payload = {
      name: values.name,
      step_id: Number(values.step_id),
      enable_stagnant_days: values.enable_stagnant_days,
      stagnant_days: values.enable_stagnant_days ? Number(values.stagnant_days) : null,
    };
    try {
      if (editingStage) {
        await updateStage(editingStage.id, { ...payload, is_active: editingStage.is_active });
      } else {
        await createStage(payload);
      }
      setModalOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["stages"] });
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  async function handleConfirmDelete(): Promise<void> {
    if (!pendingDelete) return;
    await deleteStage(pendingDelete.id);
    setPendingDelete(null);
    await queryClient.invalidateQueries({ queryKey: ["stages"] });
  }

  async function handleReorder(orderedIds: string[]): Promise<void> {
    await reorderStages(orderedIds);
    await queryClient.invalidateQueries({ queryKey: ["stages"] });
  }

  const columns: DataTableColumn<StageData>[] = [
    { id: "name", header: "Etapa", cell: (row) => row.name },
    { id: "step_name", header: "Classificação", cell: (row) => row.step_name },
    {
      id: "enable_stagnant_days",
      header: "Estagnação",
      cell: (row) => (row.enable_stagnant_days ? `${row.stagnant_days} dia(s)` : "Desativada"),
    },
    {
      id: "created_at",
      header: "Cadastro",
      cell: (row) => new Date(row.created_at).toLocaleDateString("pt-BR"),
    },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Etapas</h1>
        {isGestor && <Button onClick={openCreateModal}>Nova etapa</Button>}
      </div>

      <FilterBar fields={filterFields} />

      {isGestor && stepId !== undefined && (
        <Button variant="outline" size="sm" onClick={() => setReorderMode((current) => !current)}>
          {reorderMode ? "Concluir reordenação" : "Reordenar etapas desta fase"}
        </Button>
      )}

      {reorderMode && stepId !== undefined ? (
        <StageReorderList stages={stages} onReorder={handleReorder} />
      ) : (
        <DataTable
          columns={columns}
          data={stages}
          getRowId={(row) => row.id}
          isLoading={isLoading}
          error={error instanceof ApiError ? error.message : null}
          emptyMessage="Nenhuma etapa cadastrada ainda."
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
                    <button
                      type="button"
                      className="text-sm text-danger underline"
                      onClick={() => setPendingDelete(row)}
                    >
                      Excluir
                    </button>
                  </div>
                )
              : undefined
          }
        />
      )}

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingStage ? "Editar etapa" : "Nova etapa"}
        schema={stageFormSchema}
        defaultValues={
          editingStage
            ? {
                name: editingStage.name,
                step_id: String(editingStage.step_id),
                enable_stagnant_days: editingStage.enable_stagnant_days,
                stagnant_days: editingStage.stagnant_days ? String(editingStage.stagnant_days) : "",
              }
            : DEFAULT_STAGE_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => <StageForm form={form} steps={steps} />}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir etapa?"
        description={`"${pendingDelete?.name ?? ""}" será excluída.`}
        confirmLabel="Excluir"
        destructive
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

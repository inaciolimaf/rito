import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useFilters } from "@/components/domain/useFilters";
import { listActionGroups } from "@/features/action-groups/api";
import {
  createLawsuitType,
  deleteLawsuitType,
  listLawsuitTypes,
  updateLawsuitType,
  type LawsuitTypeData,
} from "@/features/lawsuit-types/api";
import { LawsuitTypeForm } from "@/features/lawsuit-types/LawsuitTypeForm";
import {
  DEFAULT_LAWSUIT_TYPE_FORM_VALUES,
  lawsuitTypeFormSchema,
  type LawsuitTypeFormValues,
} from "@/features/lawsuit-types/schema";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

export function LawsuitTypesListPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";

  const { data: groupsPage } = useQuery({
    queryKey: ["action-groups", "for-lawsuit-type-filter"],
    queryFn: () => listActionGroups({}),
  });
  const groups = groupsPage?.items ?? [];

  const filterFields: FilterFieldDef[] = [
    {
      key: "group_id",
      label: "Grupo de ação",
      type: "select",
      options: groups.map((group) => ({ value: group.id, label: group.name })),
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
  const groupId = typeof values.group_id === "string" ? values.group_id : undefined;
  const status =
    typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined;
  const q = typeof values.q === "string" ? values.q : undefined;

  const { data, isLoading, error } = useQuery({
    queryKey: ["lawsuit-types", { groupId, status, q }],
    queryFn: () => listLawsuitTypes({ group_id: groupId, status, q }),
  });

  const {
    editing: editingType,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
    handleConfirmDelete,
  } = useCrudResource<LawsuitTypeData, LawsuitTypeFormValues>({
    queryKey: ["lawsuit-types"],
    create: createLawsuitType,
    update: (lawsuitType, values) =>
      updateLawsuitType(lawsuitType.id, { ...values, is_active: lawsuitType.is_active }),
    remove: (lawsuitType) => deleteLawsuitType(lawsuitType.id),
  });

  const columns: DataTableColumn<LawsuitTypeData>[] = [
    { id: "name", header: "Nome", cell: (row) => row.name },
    { id: "action_group_name", header: "Grupo de ação", cell: (row) => row.action_group_name },
    { id: "is_active", header: "Status", cell: (row) => (row.is_active ? "Ativo" : "Inativo") },
    {
      id: "created_at",
      header: "Cadastro",
      cell: (row) => new Date(row.created_at).toLocaleDateString("pt-BR"),
    },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Tipos de ação</h1>
        {isGestor && <Button onClick={openCreateModal}>Novo tipo de ação</Button>}
      </div>

      <FilterBar fields={filterFields} />

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum tipo de ação cadastrado ainda."
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

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingType ? "Editar tipo de ação" : "Novo tipo de ação"}
        schema={lawsuitTypeFormSchema}
        defaultValues={
          editingType
            ? { name: editingType.name, action_group_id: editingType.action_group_id }
            : DEFAULT_LAWSUIT_TYPE_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => <LawsuitTypeForm form={form} groups={groups} />}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir tipo de ação?"
        description={`"${pendingDelete?.name ?? ""}" será excluído.`}
        confirmLabel="Excluir"
        destructive
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

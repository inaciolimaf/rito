import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import { TransferBeforeDeleteDialog } from "@/components/domain/TransferBeforeDeleteDialog";
import type { DataTableColumn, EntityOption, FilterFieldDef } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useFilters } from "@/components/domain/useFilters";
import {
  createActionGroup,
  deleteActionGroup,
  listActionGroups,
  updateActionGroup,
  type ActionGroupData,
} from "@/features/action-groups/api";
import { ActionGroupForm } from "@/features/action-groups/ActionGroupForm";
import {
  actionGroupFormSchema,
  DEFAULT_ACTION_GROUP_FORM_VALUES,
  type ActionGroupFormValues,
} from "@/features/action-groups/schema";
import { transferLawsuitTypes } from "@/features/lawsuit-types/api";
import { listUsers } from "@/features/users/api";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

const FILTER_FIELDS: FilterFieldDef[] = [
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

export function ActionGroupsListPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";
  const queryClient = useQueryClient();

  const { values } = useFilters(FILTER_FIELDS);
  const status =
    typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined;
  const q = typeof values.q === "string" ? values.q : undefined;

  const [transferDialogOpen, setTransferDialogOpen] = React.useState(false);
  const [transferError, setTransferError] = React.useState<ApiError | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["action-groups", { status, q }],
    queryFn: () => listActionGroups({ status, q }),
  });
  const groups = data?.items ?? [];

  const { data: usersPage } = useQuery({
    queryKey: ["users", "for-action-group-form"],
    queryFn: () => listUsers({ limit: 100 }),
  });
  const users = usersPage?.items ?? [];

  const {
    editing: editingGroup,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
    handleConfirmDelete,
  } = useCrudResource<ActionGroupData, ActionGroupFormValues>({
    queryKey: ["action-groups"],
    create: createActionGroup,
    update: (group, values) =>
      updateActionGroup(group.id, { ...values, is_active: group.is_active }),
    remove: (group) => deleteActionGroup(group.id),
  });

  async function searchUsers(query: string): Promise<EntityOption[]> {
    const page = await listUsers({ q: query, limit: 20 });
    return page.items.map((item) => ({ id: item.id, label: item.name }));
  }

  function requestDelete(group: ActionGroupData): void {
    setTransferError(null);
    setPendingDelete(group);
    if (group.lawsuit_types_count > 0) {
      setTransferDialogOpen(true);
    }
  }

  async function handleTransferAndDelete(destinationId: string): Promise<void> {
    if (!pendingDelete) return;
    try {
      await transferLawsuitTypes(pendingDelete.id, destinationId);
      await deleteActionGroup(pendingDelete.id);
      setPendingDelete(null);
      await queryClient.invalidateQueries({ queryKey: ["action-groups"] });
      await queryClient.invalidateQueries({ queryKey: ["lawsuit-types"] });
    } catch (submitError) {
      setTransferError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  const transferOptions: EntityOption[] = groups
    .filter((group) => group.id !== pendingDelete?.id)
    .map((group) => ({ id: group.id, label: group.name }));

  const currentResponsible: EntityOption | null = editingGroup?.publications_user_id
    ? (() => {
        const found = users.find((item) => item.id === editingGroup.publications_user_id);
        return found ? { id: found.id, label: found.name } : null;
      })()
    : null;

  const columns: DataTableColumn<ActionGroupData>[] = [
    { id: "name", header: "Nome", cell: (row) => row.name },
    {
      id: "lawsuit_types_count",
      header: "Tipos de ação",
      cell: (row) => row.lawsuit_types_count,
    },
    {
      id: "is_active",
      header: "Status",
      cell: (row) => (row.is_active ? "Ativo" : "Inativo"),
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
        <h1 className="text-lg font-semibold text-primary">Grupos de ação</h1>
        {isGestor && <Button onClick={openCreateModal}>Novo grupo</Button>}
      </div>

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={groups}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum grupo de ação cadastrado ainda."
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
                    onClick={() => requestDelete(row)}
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
        title={editingGroup ? "Editar grupo de ação" : "Novo grupo de ação"}
        schema={actionGroupFormSchema}
        defaultValues={
          editingGroup
            ? { name: editingGroup.name, publications_user_id: editingGroup.publications_user_id }
            : DEFAULT_ACTION_GROUP_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <ActionGroupForm
            form={form}
            onSearchUsers={searchUsers}
            currentResponsible={currentResponsible}
          />
        )}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null && pendingDelete.lawsuit_types_count === 0}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir grupo de ação?"
        description={`"${pendingDelete?.name ?? ""}" será excluído.`}
        confirmLabel="Excluir"
        destructive
        onConfirm={handleConfirmDelete}
      />

      <TransferBeforeDeleteDialog
        open={transferDialogOpen && pendingDelete !== null && pendingDelete.lawsuit_types_count > 0}
        onOpenChange={(open) => {
          setTransferDialogOpen(open);
          if (!open) setPendingDelete(null);
        }}
        title="Transferir tipos de ação antes de excluir"
        description={`"${pendingDelete?.name ?? ""}" tem ${pendingDelete?.lawsuit_types_count ?? 0} tipo(s) de ação vinculado(s) (regra 3). Escolha o grupo de destino — todos migram para lá antes da exclusão.`}
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

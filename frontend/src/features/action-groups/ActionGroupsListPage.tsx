import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { CrudListPage } from "@/components/domain/CrudListPage";
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

  const crud = useCrudResource<ActionGroupData, ActionGroupFormValues>({
    queryKey: ["action-groups"],
    create: createActionGroup,
    update: (group, values) =>
      updateActionGroup(group.id, { ...values, is_active: group.is_active }),
    remove: (group) => deleteActionGroup(group.id),
  });
  const { editing: editingGroup, pendingDelete, setPendingDelete } = crud;

  async function searchUsers(query: string): Promise<EntityOption[]> {
    const page = await listUsers({ q: query, limit: 20 });
    return page.items.map((item) => ({ id: item.id, label: item.name }));
  }

  /** Diferente das outras taxonomias, o grupo de ação já sabe pela listagem quantos tipos
   * dependem dele (`lawsuit_types_count`) — então a tela decide pelo contador, sem tentar
   * o DELETE primeiro (spec 101, §useTransferBeforeDelete). */
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
    <CrudListPage
      title="Grupos de ação"
      createLabel="Novo grupo"
      canWrite={isGestor}
      filterFields={FILTER_FIELDS}
      columns={columns}
      data={groups}
      isLoading={isLoading}
      error={error}
      emptyMessage="Nenhum grupo de ação cadastrado ainda."
      crud={crud}
      onDeleteRequest={requestDelete}
      createTitle="Novo grupo de ação"
      editTitle="Editar grupo de ação"
      schema={actionGroupFormSchema}
      emptyFormValues={DEFAULT_ACTION_GROUP_FORM_VALUES}
      toFormValues={(group) => ({
        name: group.name,
        publications_user_id: group.publications_user_id,
      })}
      formFields={(form) => (
        <ActionGroupForm
          form={form}
          onSearchUsers={searchUsers}
          currentResponsible={currentResponsible}
        />
      )}
      confirmTitle="Excluir grupo de ação?"
      confirmDescription={(item) => `"${item?.name ?? ""}" será excluído.`}
      isDeletableWithoutTransfer={(group) => group.lawsuit_types_count === 0}
    >
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
    </CrudListPage>
  );
}

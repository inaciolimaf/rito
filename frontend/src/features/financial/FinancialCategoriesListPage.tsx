import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, EntityOption, FilterFieldDef } from "@/components/domain/types";
import { TransferBeforeDeleteDialog } from "@/components/domain/TransferBeforeDeleteDialog";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useTransferBeforeDelete } from "@/components/domain/useTransferBeforeDelete";
import { useFilters } from "@/components/domain/useFilters";
import { CategoryForm } from "@/features/financial/CategoryForm";
import { DreGroupBadge } from "@/features/financial/DreGroupBadge";
import {
  createFinancialCategory,
  deleteFinancialCategory,
  listDreGroups,
  listFinancialCategories,
  transferFinancialCategories,
  updateFinancialCategory,
  type EntryType,
  type FinancialCategoryData,
} from "@/features/financial/api";
import {
  DEFAULT_FINANCIAL_CATEGORY_FORM_VALUES,
  financialCategoryFormSchema,
  type FinancialCategoryFormValues,
} from "@/features/financial/schema";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

const FILTER_FIELDS: FilterFieldDef[] = [
  {
    key: "type",
    label: "Tipo",
    type: "select",
    options: [
      { value: "RECEITA", label: "Receita" },
      { value: "DESPESA", label: "Despesa" },
    ],
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

/** Regra 6 (spec 054): escrita exige financial_access=FULL **e** GESTOR — as duas
 * dimensões, não uma OR a outra. */
export function FinancialCategoriesListPage(): JSX.Element {
  const { user } = useAuth();
  const canWrite = user?.role === "GESTOR" && user?.financialAccess === "FULL";

  const { values } = useFilters(FILTER_FIELDS);
  const type = typeof values.type === "string" ? (values.type as EntryType) : undefined;
  const status =
    typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined;
  const q = typeof values.q === "string" ? values.q : undefined;

  const { data: groups = [] } = useQuery({ queryKey: ["dre-groups"], queryFn: listDreGroups });

  const { data, isLoading, error } = useQuery({
    queryKey: ["financial-categories", { type, status, q }],
    queryFn: () => listFinancialCategories({ type, status, q }),
  });
  const categories = data?.items ?? [];

  const {
    editing: editingCategory,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
  } = useCrudResource<FinancialCategoryData, FinancialCategoryFormValues>({
    queryKey: ["financial-categories"],
    create: (values) =>
      createFinancialCategory({ ...values, dre_group_id: Number(values.dre_group_id) }),
    update: (category, values) =>
      updateFinancialCategory(category.id, {
        ...values,
        dre_group_id: Number(values.dre_group_id),
        is_active: category.is_active,
      }),
    remove: (category) => deleteFinancialCategory(category.id),
  });

  // Spec 101, regras 7-8: categoria com lançamento vinculado devolve 409.
  const transferFlow = useTransferBeforeDelete<FinancialCategoryData>({
    queryKey: ["financial-categories"],
    remove: (category) => deleteFinancialCategory(category.id),
    transfer: async (category, destinationId) => {
      await transferFinancialCategories(category.id, destinationId);
    },
    alsoInvalidate: [["transactions"]],
  });

  const transferOptions: EntityOption[] = categories
    .filter((category) => category.id !== transferFlow.pendingTransfer?.id)
    .map((category) => ({ id: category.id, label: category.name }));

  const columns: DataTableColumn<FinancialCategoryData>[] = [
    { id: "name", header: "Nome", cell: (row) => row.name },
    { id: "type", header: "Tipo", cell: (row) => (row.type === "RECEITA" ? "Receita" : "Despesa") },
    {
      id: "dre_group_name",
      header: "Grupo DRE",
      cell: (row) => <DreGroupBadge name={row.dre_group_name} nature={row.type} />,
    },
    {
      id: "is_default",
      header: "Origem",
      cell: (row) => (row.is_default ? "Padrão" : "Personalizada"),
    },
    {
      id: "is_active",
      header: "Status",
      cell: (row) => (row.is_active ? "Ativa" : "Inativa"),
    },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Categorias financeiras</h1>
        {canWrite && <Button onClick={openCreateModal}>Nova categoria</Button>}
      </div>

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={categories}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhuma categoria cadastrada ainda."
        rowActions={
          canWrite
            ? (row) => (
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-sm text-accent underline"
                    onClick={() => openEditModal(row)}
                  >
                    Editar
                  </button>
                  {!row.is_default && (
                    <button
                      type="button"
                      className="text-sm text-danger underline"
                      onClick={() => setPendingDelete(row)}
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
        title={editingCategory ? "Editar categoria" : "Nova categoria"}
        schema={financialCategoryFormSchema}
        defaultValues={
          editingCategory
            ? {
                name: editingCategory.name,
                type: editingCategory.type,
                dre_group_id: String(editingCategory.dre_group_id),
              }
            : DEFAULT_FINANCIAL_CATEGORY_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => <CategoryForm form={form} groups={groups} />}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir categoria?"
        description={`"${pendingDelete?.name ?? ""}" será excluída.`}
        confirmLabel="Excluir"
        destructive
        onConfirm={async () => {
          const alvo = pendingDelete;
          if (!alvo) return;
          setPendingDelete(null);
          await transferFlow.requestDelete(alvo);
        }}
      />

      <TransferBeforeDeleteDialog
        open={transferFlow.dialogOpen}
        onOpenChange={(open) => {
          if (!open) transferFlow.closeDialog();
        }}
        title="Transferir lançamentos antes de excluir"
        description={`"${transferFlow.pendingTransfer?.name ?? ""}" tem lançamentos vinculados (regra 7). Escolha a categoria de destino — todos migram para lá antes da exclusão.`}
        options={transferOptions}
        onTransfer={transferFlow.transferAndDelete}
      />
      {transferFlow.transferError && (
        <p role="alert" className="text-sm text-danger">
          {transferFlow.transferError.message}
        </p>
      )}
    </div>
  );
}

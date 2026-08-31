import { useQuery } from "@tanstack/react-query";
import type { UseFormReturn } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, EntityOption, FilterFieldDef } from "@/components/domain/types";
import { TransferBeforeDeleteDialog } from "@/components/domain/TransferBeforeDeleteDialog";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useTransferBeforeDelete } from "@/components/domain/useTransferBeforeDelete";
import { useFilters } from "@/components/domain/useFilters";
import {
  createCostCenter,
  deleteCostCenter,
  listCostCenters,
  transferCostCenters,
  updateCostCenter,
  type CostCenterData,
} from "@/features/financial/api";
import {
  costCenterFormSchema,
  DEFAULT_COST_CENTER_FORM_VALUES,
  type CostCenterFormValues,
} from "@/features/financial/schema";
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

function CostCenterForm({ form }: { form: UseFormReturn<CostCenterFormValues> }): JSX.Element {
  const {
    register,
    formState: { errors },
  } = form;
  return (
    <div className="space-y-1">
      <Label htmlFor="cost-center-name">Nome do centro de custo</Label>
      <Input id="cost-center-name" {...register("name")} />
      {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
    </div>
  );
}

/** Regra 8 (spec 054): escrita só exige financial_access=FULL — sem GESTOR, diferente
 * de categorias (§6 do backend não lista o papel aqui). */
export function CostCentersListPage(): JSX.Element {
  const { user } = useAuth();
  const canWrite = user?.financialAccess === "FULL";

  const { values } = useFilters(FILTER_FIELDS);
  const status =
    typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined;
  const q = typeof values.q === "string" ? values.q : undefined;

  const { data, isLoading, error } = useQuery({
    queryKey: ["cost-centers", { status, q }],
    queryFn: () => listCostCenters({ status, q }),
  });
  const costCenters = data?.items ?? [];

  const {
    editing: editingCostCenter,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
  } = useCrudResource<CostCenterData, CostCenterFormValues>({
    queryKey: ["cost-centers"],
    create: createCostCenter,
    update: (costCenter, values) =>
      updateCostCenter(costCenter.id, { ...values, is_active: costCenter.is_active }),
    remove: (costCenter) => deleteCostCenter(costCenter.id),
  });

  // Spec 101, regras 7-8: centro com lançamento vinculado devolve 409.
  const transferFlow = useTransferBeforeDelete<CostCenterData>({
    queryKey: ["cost-centers"],
    remove: (costCenter) => deleteCostCenter(costCenter.id),
    transfer: async (costCenter, destinationId) => {
      await transferCostCenters(costCenter.id, destinationId);
    },
    alsoInvalidate: [["transactions"]],
  });

  const transferOptions: EntityOption[] = costCenters
    .filter((costCenter) => costCenter.id !== transferFlow.pendingTransfer?.id)
    .map((costCenter) => ({ id: costCenter.id, label: costCenter.name }));

  const columns: DataTableColumn<CostCenterData>[] = [
    { id: "name", header: "Nome", cell: (row) => row.name },
    {
      id: "is_default",
      header: "Origem",
      cell: (row) => (row.is_default ? "Padrão" : "Personalizado"),
    },
    { id: "is_active", header: "Status", cell: (row) => (row.is_active ? "Ativo" : "Inativo") },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Centros de custo</h1>
        {canWrite && <Button onClick={openCreateModal}>Novo centro de custo</Button>}
      </div>

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={costCenters}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum centro de custo cadastrado ainda."
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
        title={editingCostCenter ? "Editar centro de custo" : "Novo centro de custo"}
        schema={costCenterFormSchema}
        defaultValues={
          editingCostCenter ? { name: editingCostCenter.name } : DEFAULT_COST_CENTER_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => <CostCenterForm form={form} />}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir centro de custo?"
        description={`"${pendingDelete?.name ?? ""}" será excluído.`}
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
        description={`"${transferFlow.pendingTransfer?.name ?? ""}" tem lançamentos vinculados (regra 7). Escolha o centro de destino — todos migram para lá antes da exclusão.`}
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

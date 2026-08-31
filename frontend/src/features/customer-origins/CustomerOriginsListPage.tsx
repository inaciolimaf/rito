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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createCustomerOrigin,
  deleteCustomerOrigin,
  listCustomerOrigins,
  transferCustomerOrigins,
  updateCustomerOrigin,
  type CustomerOriginData,
} from "@/features/customer-origins/api";
import {
  customerOriginFormSchema,
  DEFAULT_CUSTOMER_ORIGIN_FORM_VALUES,
  type CustomerOriginFormValues,
} from "@/features/customer-origins/schema";
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

export function CustomerOriginsListPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";

  const { values } = useFilters(FILTER_FIELDS);
  const status =
    typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined;
  const q = typeof values.q === "string" ? values.q : undefined;

  const { data, isLoading, error } = useQuery({
    queryKey: ["customer-origins", { status, q }],
    queryFn: () => listCustomerOrigins({ status, q }),
  });

  const {
    editing: editingOrigin,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
  } = useCrudResource<CustomerOriginData, CustomerOriginFormValues>({
    queryKey: ["customer-origins"],
    create: createCustomerOrigin,
    update: (origin, values) =>
      updateCustomerOrigin(origin.id, { ...values, is_active: origin.is_active }),
    remove: (origin) => deleteCustomerOrigin(origin.id),
  });

  // Spec 101, regras 3-4: origem com contato vinculado devolve 409.
  const transferFlow = useTransferBeforeDelete<CustomerOriginData>({
    queryKey: ["customer-origins"],
    remove: (origin) => deleteCustomerOrigin(origin.id),
    transfer: async (origin, destinationId) => {
      await transferCustomerOrigins(origin.id, destinationId);
    },
    alsoInvalidate: [["customers"]],
  });

  const transferOptions: EntityOption[] = (data?.items ?? [])
    .filter((origin) => origin.id !== transferFlow.pendingTransfer?.id)
    .map((origin) => ({ id: origin.id, label: origin.name }));

  const columns: DataTableColumn<CustomerOriginData>[] = [
    { id: "name", header: "Origem", cell: (row) => row.name },
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
        <h1 className="text-lg font-semibold text-primary">Origem de pessoas</h1>
        {isGestor && <Button onClick={openCreateModal}>Nova origem</Button>}
      </div>

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhuma origem cadastrada ainda."
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
        title={editingOrigin ? "Editar origem" : "Nova origem"}
        schema={customerOriginFormSchema}
        defaultValues={
          editingOrigin ? { name: editingOrigin.name } : DEFAULT_CUSTOMER_ORIGIN_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <div className="space-y-1">
            <Label htmlFor="customer-origin-name">Nome da origem</Label>
            <Input id="customer-origin-name" {...form.register("name")} />
            {form.formState.errors.name && (
              <p className="text-sm text-danger">{form.formState.errors.name.message}</p>
            )}
          </div>
        )}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir origem?"
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
        title="Transferir contatos antes de excluir"
        description={`"${transferFlow.pendingTransfer?.name ?? ""}" tem contatos vinculados (regra 3). Escolha a origem de destino — todos migram para lá antes da exclusão.`}
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

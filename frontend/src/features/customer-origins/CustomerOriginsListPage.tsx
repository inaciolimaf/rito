import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createCustomerOrigin,
  deleteCustomerOrigin,
  listCustomerOrigins,
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
  const queryClient = useQueryClient();

  const { values } = useFilters(FILTER_FIELDS);
  const status =
    typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined;
  const q = typeof values.q === "string" ? values.q : undefined;

  const [editingOrigin, setEditingOrigin] = React.useState<CustomerOriginData | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);
  const [formError, setFormError] = React.useState<ApiError | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<CustomerOriginData | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["customer-origins", { status, q }],
    queryFn: () => listCustomerOrigins({ status, q }),
  });

  function openCreateModal(): void {
    setEditingOrigin(null);
    setFormError(null);
    setModalOpen(true);
  }

  function openEditModal(origin: CustomerOriginData): void {
    setEditingOrigin(origin);
    setFormError(null);
    setModalOpen(true);
  }

  async function handleSubmit(values: CustomerOriginFormValues): Promise<void> {
    setFormError(null);
    try {
      if (editingOrigin) {
        await updateCustomerOrigin(editingOrigin.id, {
          ...values,
          is_active: editingOrigin.is_active,
        });
      } else {
        await createCustomerOrigin(values);
      }
      setModalOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["customer-origins"] });
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  async function handleConfirmDelete(): Promise<void> {
    if (!pendingDelete) return;
    await deleteCustomerOrigin(pendingDelete.id);
    setPendingDelete(null);
    await queryClient.invalidateQueries({ queryKey: ["customer-origins"] });
  }

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
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

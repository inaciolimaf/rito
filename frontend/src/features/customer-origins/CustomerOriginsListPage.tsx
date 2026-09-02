import { useQuery } from "@tanstack/react-query";

import { CrudListPage } from "@/components/domain/CrudListPage";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
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

  const crud = useCrudResource<CustomerOriginData, CustomerOriginFormValues>({
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
    <CrudListPage
      title="Origem de pessoas"
      createLabel="Nova origem"
      canWrite={isGestor}
      filterFields={FILTER_FIELDS}
      columns={columns}
      data={data?.items ?? []}
      isLoading={isLoading}
      error={error}
      emptyMessage="Nenhuma origem cadastrada ainda."
      crud={crud}
      createTitle="Nova origem"
      editTitle="Editar origem"
      schema={customerOriginFormSchema}
      emptyFormValues={DEFAULT_CUSTOMER_ORIGIN_FORM_VALUES}
      toFormValues={(origin) => ({ name: origin.name })}
      formFields={(form) => (
        <div className="space-y-1">
          <Label htmlFor="customer-origin-name">Nome da origem</Label>
          <Input id="customer-origin-name" {...form.register("name")} />
          {form.formState.errors.name && (
            <p className="text-sm text-danger">{form.formState.errors.name.message}</p>
          )}
        </div>
      )}
      confirmTitle="Excluir origem?"
      confirmDescription={(item) => `"${item?.name ?? ""}" será excluída.`}
      transfer={{
        flow: transferFlow,
        title: "Transferir contatos antes de excluir",
        description: (item) =>
          `"${item?.name ?? ""}" tem contatos vinculados (regra 3). Escolha a origem de destino — todos migram para lá antes da exclusão.`,
      }}
    />
  );
}

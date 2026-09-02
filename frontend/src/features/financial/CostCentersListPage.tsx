import { useQuery } from "@tanstack/react-query";
import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { CrudListPage } from "@/components/domain/CrudListPage";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
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

  const crud = useCrudResource<CostCenterData, CostCenterFormValues>({
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
    <CrudListPage
      title="Centros de custo"
      createLabel="Novo centro de custo"
      canWrite={canWrite}
      filterFields={FILTER_FIELDS}
      columns={columns}
      data={costCenters}
      isLoading={isLoading}
      error={error}
      emptyMessage="Nenhum centro de custo cadastrado ainda."
      crud={crud}
      canDeleteRow={(row) => !row.is_default}
      createTitle="Novo centro de custo"
      editTitle="Editar centro de custo"
      schema={costCenterFormSchema}
      emptyFormValues={DEFAULT_COST_CENTER_FORM_VALUES}
      toFormValues={(costCenter) => ({ name: costCenter.name })}
      formFields={(form) => <CostCenterForm form={form} />}
      confirmTitle="Excluir centro de custo?"
      confirmDescription={(item) => `"${item?.name ?? ""}" será excluído.`}
      transfer={{
        flow: transferFlow,
        title: "Transferir lançamentos antes de excluir",
        description: (item) =>
          `"${item?.name ?? ""}" tem lançamentos vinculados (regra 7). Escolha o centro de destino — todos migram para lá antes da exclusão.`,
      }}
    />
  );
}

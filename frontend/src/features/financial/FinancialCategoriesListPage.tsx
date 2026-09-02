import { useQuery } from "@tanstack/react-query";

import { CrudListPage } from "@/components/domain/CrudListPage";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
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

  const crud = useCrudResource<FinancialCategoryData, FinancialCategoryFormValues>({
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
    <CrudListPage
      title="Categorias financeiras"
      createLabel="Nova categoria"
      canWrite={canWrite}
      filterFields={FILTER_FIELDS}
      columns={columns}
      data={categories}
      isLoading={isLoading}
      error={error}
      emptyMessage="Nenhuma categoria cadastrada ainda."
      crud={crud}
      canDeleteRow={(row) => !row.is_default}
      createTitle="Nova categoria"
      editTitle="Editar categoria"
      schema={financialCategoryFormSchema}
      emptyFormValues={DEFAULT_FINANCIAL_CATEGORY_FORM_VALUES}
      toFormValues={(category) => ({
        name: category.name,
        type: category.type,
        dre_group_id: String(category.dre_group_id),
      })}
      formFields={(form) => <CategoryForm form={form} groups={groups} />}
      confirmTitle="Excluir categoria?"
      confirmDescription={(item) => `"${item?.name ?? ""}" será excluída.`}
      transfer={{
        flow: transferFlow,
        title: "Transferir lançamentos antes de excluir",
        description: (item) =>
          `"${item?.name ?? ""}" tem lançamentos vinculados (regra 7). Escolha a categoria de destino — todos migram para lá antes da exclusão.`,
      }}
    />
  );
}

import { useQuery } from "@tanstack/react-query";

import { CrudListPage } from "@/components/domain/CrudListPage";
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

  const crud = useCrudResource<LawsuitTypeData, LawsuitTypeFormValues>({
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
    <CrudListPage
      title="Tipos de ação"
      createLabel="Novo tipo de ação"
      canWrite={isGestor}
      filterFields={filterFields}
      columns={columns}
      data={data?.items ?? []}
      isLoading={isLoading}
      error={error}
      emptyMessage="Nenhum tipo de ação cadastrado ainda."
      crud={crud}
      createTitle="Novo tipo de ação"
      editTitle="Editar tipo de ação"
      schema={lawsuitTypeFormSchema}
      emptyFormValues={DEFAULT_LAWSUIT_TYPE_FORM_VALUES}
      toFormValues={(lawsuitType) => ({
        name: lawsuitType.name,
        action_group_id: lawsuitType.action_group_id,
      })}
      formFields={(form) => <LawsuitTypeForm form={form} groups={groups} />}
      confirmTitle="Excluir tipo de ação?"
      confirmDescription={(item) => `"${item?.name ?? ""}" será excluído.`}
    />
  );
}

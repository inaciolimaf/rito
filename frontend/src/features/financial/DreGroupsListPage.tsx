import { useQuery } from "@tanstack/react-query";

import { DataTable } from "@/components/domain/DataTable";
import type { DataTableColumn } from "@/components/domain/types";
import { DreGroupBadge } from "@/features/financial/DreGroupBadge";
import { listDreGroups, type DreGroupData } from "@/features/financial/api";
import { ApiError } from "@/lib/errors";

const columns: DataTableColumn<DreGroupData>[] = [
  {
    id: "name",
    header: "Grupo",
    cell: (row) => <DreGroupBadge name={row.name} nature={row.nature} />,
  },
  {
    id: "nature",
    header: "Natureza",
    cell: (row) => (row.nature === "RECEITA" ? "Receita" : "Despesa"),
  },
];

/** Regra 1 (spec 054): os 10 grupos DRE são imutáveis — só leitura, sem criar/editar/
 * excluir na UI (a API nem aceita POST/PUT/DELETE). */
export function DreGroupsListPage(): JSX.Element {
  const {
    data: groups = [],
    isLoading,
    error,
  } = useQuery({
    queryKey: ["dre-groups"],
    queryFn: listDreGroups,
  });

  return (
    <div className="space-y-4 p-6">
      <h1 className="text-lg font-semibold text-primary">Grupos DRE</h1>
      <DataTable
        columns={columns}
        data={groups}
        getRowId={(row) => String(row.id)}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum grupo DRE encontrado."
      />
    </div>
  );
}

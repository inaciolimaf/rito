import { DataTable } from "@/components/domain/DataTable";
import type { DataTableColumn } from "@/components/domain/types";
import type { TimeFeesTypeData } from "@/features/reports/api";
import { formatBrl } from "@/lib/money";

export interface ProfitabilityTableProps {
  types: TimeFeesTypeData[];
  isLoading?: boolean;
}

const COLUMNS: DataTableColumn<TimeFeesTypeData>[] = [
  { id: "lawsuit_type_name", header: "Tipo de ação", cell: (row) => row.lawsuit_type_name },
  { id: "lawsuits", header: "Processos", cell: (row) => row.lawsuits },
  {
    id: "monthly_profitability",
    header: "Rentabilidade mensal",
    cell: (row) => (
      <span className="flex items-center gap-1">
        {/* Regra 8: null (nenhum processo com rotação completa) → "—", nunca R$ 0,00. */}
        <span>{formatBrl(row.monthly_profitability)}</span>
        {/* Regra 9: menos de 5 processos no recorte. */}
        {row.small_sample && (
          <span className="text-xs text-warning" title="Amostra pequena: menos de 5 processos">
            ⚠
          </span>
        )}
      </span>
    ),
  },
];

/** Rentabilidade mensal por tipo de ação (spec 076, regra 8): média de
 * (honorários ÷ meses de duração) — a resposta à pergunta "esse tipo de ação
 * compensa?". */
export function ProfitabilityTable({
  types,
  isLoading = false,
}: ProfitabilityTableProps): JSX.Element {
  return (
    <section aria-label="Rentabilidade por tipo de ação" className="space-y-2">
      <h3 className="text-sm font-medium text-primary">Rentabilidade mensal por tipo de ação</h3>
      <DataTable
        columns={COLUMNS}
        data={types}
        getRowId={(row) => row.lawsuit_type_id}
        isLoading={isLoading}
        emptyMessage="Nenhum processo fechado no período."
      />
    </section>
  );
}

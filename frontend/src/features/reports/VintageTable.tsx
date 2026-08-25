import { DataTable } from "@/components/domain/DataTable";
import type { DataTableColumn } from "@/components/domain/types";
import type { VintageYearData } from "@/features/reports/api";
import { SmallSampleWarning } from "@/features/reports/SmallSampleWarning";

export interface VintageTableProps {
  years: VintageYearData[];
  isLoading?: boolean;
}

function formatCycleDays(value: number | null): string {
  // Regra 7: sem arquivados na safra não há ciclo médio — "—", nunca 0.
  return value === null ? "—" : `${value}d`;
}

const COLUMNS: DataTableColumn<VintageYearData>[] = [
  { id: "vintage_year", header: "Safra", cell: (row) => row.vintage_year },
  { id: "total", header: "Total", cell: (row) => row.total },
  { id: "won", header: "Ganhos", cell: (row) => row.won },
  { id: "lost", header: "Perdidos", cell: (row) => row.lost },
  { id: "settled", header: "Acordos", cell: (row) => row.settled },
  { id: "in_progress", header: "Em andamento", cell: (row) => row.in_progress },
  { id: "transited", header: "Transitados", cell: (row) => row.transited },
  { id: "archived", header: "Arquivados", cell: (row) => row.archived },
  {
    id: "avg_cycle_days",
    header: "Ciclo médio",
    cell: (row) => formatCycleDays(row.avg_cycle_days),
  },
  {
    id: "success_rate",
    header: "Taxa de sucesso",
    cell: (row) => (
      <span className="flex items-center gap-1">
        {/* Regra 11: zero concluídos → "—", nunca 0%. */}
        <span>{row.success_rate === null ? "—" : `${row.success_rate}%`}</span>
        {/* Regra 9: variação acima de 10 p.p. vs safra anterior é destacada. */}
        {row.highlighted && row.rate_change_pp !== null && (
          <span
            className="rounded bg-surface-muted px-1 text-xs text-primary"
            title={`Variação de ${row.rate_change_pp} p.p. em relação à safra anterior`}
          >
            {row.rate_change_pp > 0 ? "+" : ""}
            {row.rate_change_pp} p.p.
          </span>
        )}
        {/* Regra 5: menos de 10 concluídos na safra. */}
        {row.small_sample && row.success_rate !== null && (
          <SmallSampleWarning minimum={10} unit="concluídos" />
        )}
      </span>
    ),
  },
];

/** Tabela de safra (spec 075, regra 4): ano de fechamento × estágio atual, com os 8
 * campos + taxa de sucesso e os derivados das regras 5, 9 e 11. Safra sem fechamento
 * não aparece (regra 8 — o backend já não a devolve). */
export function VintageTable({ years, isLoading = false }: VintageTableProps): JSX.Element {
  return (
    <section aria-label="Tabela de safra" className="space-y-2">
      <h3 className="text-sm font-medium text-primary">Safra por ano de fechamento</h3>
      <DataTable
        columns={COLUMNS}
        data={years}
        getRowId={(row) => String(row.vintage_year)}
        isLoading={isLoading}
        emptyMessage="Nenhum processo fechado no período."
      />
    </section>
  );
}

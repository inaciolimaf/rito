import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { DataTable } from "@/components/domain/DataTable";
import { StatCard } from "@/components/domain/StatCard";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import {
  getBiCac,
  getBiCostPerPoint,
  getBiCosts,
  getBiCostsByStage,
  type CostLawsuitItemData,
} from "@/features/reports/api";
import { AllocationExplainer } from "@/features/reports/AllocationExplainer";
import { BiTabPanel } from "@/features/reports/BiTabPanel";
import { CacCard } from "@/features/reports/CacCard";
import { CostPerPointCard } from "@/features/reports/CostPerPointCard";
import { CostPerStageChart } from "@/features/reports/CostPerStageChart";
import { formatBrl } from "@/lib/money";

const COST_COLUMNS: DataTableColumn<CostLawsuitItemData>[] = [
  {
    id: "folder",
    header: "Processo",
    cell: (row) => (
      <span className="flex items-center gap-1">
        <span className="truncate">{row.folder ?? row.process_number ?? "—"}</span>
        {/* Regra 6: processo em andamento entra no cálculo — o selo deixa isso claro. */}
        {row.in_progress && (
          <span className="rounded bg-surface-muted px-1 text-xs text-muted">em andamento</span>
        )}
      </span>
    ),
  },
  { id: "direct_cost", header: "Custo direto", cell: (row) => formatBrl(row.direct_cost) },
  { id: "points", header: "Pontos", cell: (row) => row.points },
  {
    id: "points_cost",
    header: "Rateio (pontos)",
    // Regra 8: mês sem custo por ponto calculável → "—", nunca R$ 0,00 nem infinito.
    cell: (row) => formatBrl(row.points_cost),
  },
  {
    id: "allocated_cost",
    header: "Custo alocado",
    cell: (row) => <span className="font-medium">{formatBrl(row.allocated_cost)}</span>,
  },
];

/** Aba "Custos" do BI (spec 077): CAC (regra 1), custo por ponto (regra 2), tempo e
 * custo médio por etapa (regra 10) e a tabela de custo por processo — direto + rateio
 * dos pontos (regras 4 e 5), com processos em andamento (regra 6). Custo fixo,
 * marketing e custo por ponto vêm da view bi_cost_allocation (até 8 h de defasagem,
 * sinalizada no rodapé); o resto é tempo real. */
export function CostsPanel(): JSX.Element {
  const filterFields = React.useMemo<FilterFieldDef[]>(
    () => [
      {
        key: "outcome",
        label: "Resultado",
        type: "select",
        options: [
          { value: "GANHO", label: "Ganhos" },
          { value: "PERDIDO", label: "Perdidos" },
          { value: "ACORDO", label: "Acordos" },
        ],
      },
      // Regra 7: o intervalo de anos usa archived_date; sem arquivamento, created_at.
      { key: "from_year", label: "Ano de", type: "text" },
      { key: "to_year", label: "Ano até", type: "text" },
      { key: "period", label: "Competência (AAAA-MM)", type: "text" },
    ],
    [],
  );
  const { values } = useFilters(filterFields);
  const outcome = typeof values.outcome === "string" ? values.outcome : undefined;
  const fromYear =
    typeof values.from_year === "string" && /^\d{4}$/.test(values.from_year)
      ? Number(values.from_year)
      : undefined;
  const toYear =
    typeof values.to_year === "string" && /^\d{4}$/.test(values.to_year)
      ? Number(values.to_year)
      : undefined;
  const period =
    typeof values.period === "string" && /^\d{4}-\d{2}$/.test(values.period)
      ? values.period
      : undefined;

  const { data: costs, isLoading } = useQuery({
    queryKey: ["bi-costs", outcome, fromYear, toYear],
    queryFn: () => getBiCosts({ outcome, fromYear, toYear }),
  });
  const { data: cac, isLoading: isLoadingCac } = useQuery({
    queryKey: ["bi-cac", period],
    queryFn: () => getBiCac(period),
  });
  const { data: perPoint, isLoading: isLoadingPerPoint } = useQuery({
    queryKey: ["bi-cost-per-point", period],
    queryFn: () => getBiCostPerPoint(period),
  });
  const { data: byStage } = useQuery({
    queryKey: ["bi-costs-by-stage"],
    queryFn: () => getBiCostsByStage(),
  });

  const allocationNote = costs?.allocation_note ?? byStage?.allocation_note ?? "";

  return (
    <BiTabPanel
      filterFields={filterFields}
      stalenessHint={costs?.staleness_hint}
      cards={
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <CacCard data={cac} isLoading={isLoadingCac} />
          <CostPerPointCard data={perPoint} isLoading={isLoadingPerPoint} />
          <StatCard
            label="Custo direto total"
            value={formatBrl(costs?.total_direct ?? null)}
            isLoading={isLoading}
          />
          <StatCard
            label="Custo alocado total"
            value={formatBrl(costs?.total_allocated ?? null)}
            isLoading={isLoading}
          />
        </div>
      }
    >
      <CostPerStageChart stages={byStage?.stages ?? []} />

      <section aria-label="Custo por processo" className="space-y-2">
        <h3 className="flex items-center gap-1 text-sm font-medium text-primary">
          Custo por processo
          {/* Regra 11: o rateio é aproximação — o tooltip explica a fórmula. */}
          <AllocationExplainer note={allocationNote} />
        </h3>
        <DataTable
          columns={COST_COLUMNS}
          data={costs?.items ?? []}
          getRowId={(row) => row.lawsuit_id}
          isLoading={isLoading}
          emptyMessage="Nenhum processo no recorte."
        />
      </section>
    </BiTabPanel>
  );
}

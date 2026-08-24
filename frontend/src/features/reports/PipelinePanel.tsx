import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { DataTable } from "@/components/domain/DataTable";
import { DonutChart } from "@/components/domain/DonutChart";
import { FilterBar } from "@/components/domain/FilterBar";
import { StatCard } from "@/components/domain/StatCard";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { listActionGroups } from "@/features/action-groups/api";
import { BiRefreshIndicator } from "@/features/reports/BiRefreshIndicator";
import { ConversionFunnel } from "@/features/reports/ConversionFunnel";
import { SixMonthTrend } from "@/features/reports/SixMonthTrend";
import { StaleWarning } from "@/features/reports/StaleWarning";
import {
  getBiConversion,
  getBiPipeline,
  getBiPortfolio,
  type BiPipelineData,
  type PortfolioGroupBy,
  type PortfolioPeriodItemData,
  type PortfolioStepItemData,
} from "@/features/reports/api";

function currentMonthQuery(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function monthLabel(isoMonth: string): string {
  const [year, month] = isoMonth.split("-");
  return `${month}/${year}`;
}

function closedVariation(
  closedMonth: BiPipelineData["closed_month"],
): { label: string; trend: "up" | "down" | "flat" } | null {
  const { value, delta_pct } = closedMonth;
  // Mês anterior zerado → "novo" (regra 5 + divisão por zero, mesmo idioma da 028).
  if (delta_pct === null) return value > 0 ? { label: "novo", trend: "up" } : null;
  return {
    label: `${delta_pct > 0 ? "+" : ""}${delta_pct}% vs. mês anterior`,
    trend: delta_pct > 0 ? "up" : delta_pct < 0 ? "down" : "flat",
  };
}

const STEP_COLUMNS: DataTableColumn<PortfolioStepItemData>[] = [
  { id: "step_name", header: "Fase", cell: (row) => row.step_name },
  { id: "active", header: "Ativos", cell: (row) => row.active },
];

const PERIOD_COLUMNS: DataTableColumn<PortfolioPeriodItemData>[] = [
  { id: "month", header: "Mês de criação", cell: (row) => monthLabel(row.month) },
  { id: "active", header: "Ativos", cell: (row) => row.active },
];

/** Aba "Estoque e Prospecção" do BI (spec 074): os 6 indicadores, funil de conversão
 * por grupo, série de 6 meses e o resumo da carteira (tempo real) no rodapé. */
export function PipelinePanel(): JSX.Element {
  const [portfolioGroupBy, setPortfolioGroupBy] = React.useState<PortfolioGroupBy>("step");

  const { data: actionGroups } = useQuery({
    queryKey: ["action-groups", "active"],
    queryFn: () => listActionGroups({ status: "active" }),
  });

  const filterFields = React.useMemo<FilterFieldDef[]>(
    () => [
      { key: "from", label: "De", type: "date" },
      { key: "to", label: "Até", type: "date" },
      {
        key: "action_group_id",
        label: "Grupo de ação",
        type: "select",
        options: (actionGroups?.items ?? []).map((group) => ({
          value: group.id,
          label: group.name,
        })),
      },
    ],
    [actionGroups],
  );
  const { values } = useFilters(filterFields);
  const from = typeof values.from === "string" ? values.from : undefined;
  const to = typeof values.to === "string" ? values.to : undefined;
  const actionGroupId =
    typeof values.action_group_id === "string" ? values.action_group_id : undefined;

  const { data, isLoading } = useQuery({
    queryKey: ["bi-pipeline", from, to, actionGroupId],
    queryFn: () => getBiPipeline({ from, to, actionGroupId }),
  });

  const period = from ? from.slice(0, 7) : currentMonthQuery();
  const { data: conversion, isLoading: isLoadingConversion } = useQuery({
    queryKey: ["bi-conversion", period],
    queryFn: () => getBiConversion(period),
  });

  const { data: portfolio, isLoading: isLoadingPortfolio } = useQuery({
    queryKey: ["bi-portfolio", portfolioGroupBy, actionGroupId],
    queryFn: () => getBiPortfolio(portfolioGroupBy, { actionGroupId }),
  });

  return (
    <div className="space-y-4">
      <FilterBar fields={filterFields} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard
          label="Oportunidades do mês"
          value={data?.opportunities_month ?? 0}
          isLoading={isLoading}
        />
        <StatCard label="Processos ativos" value={data?.active ?? 0} isLoading={isLoading} />
        <StatCard label="Arquivados" value={data?.archived ?? 0} isLoading={isLoading} />
        <StatCard label="Parados +120 dias" value={data?.idle_120 ?? 0} isLoading={isLoading} />
        <StatCard
          label="Fechamentos do mês"
          value={data?.closed_month.value ?? 0}
          isLoading={isLoading}
          variation={data ? closedVariation(data.closed_month) : null}
        />
        <StatCard label="Em atendimento" value={data?.in_service ?? 0} isLoading={isLoading} />
      </div>

      {data && <StaleWarning idleCount={data.idle_120} />}

      <div className="grid gap-4 lg:grid-cols-2">
        <ConversionFunnel groups={conversion?.groups ?? []} isLoading={isLoadingConversion} />
        <SixMonthTrend points={data?.closed_trend ?? []} />
      </div>

      <section aria-label="Resumo da carteira" className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-primary">Resumo da carteira</h3>
          <div className="flex gap-1" role="group" aria-label="Agrupar por">
            {(
              [
                { value: "step", label: "Por fase" },
                { value: "period", label: "Por período" },
              ] as const
            ).map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={portfolioGroupBy === option.value}
                className={
                  portfolioGroupBy === option.value
                    ? "rounded border border-accent px-2 py-1 text-xs text-primary"
                    : "rounded border border-default px-2 py-1 text-xs text-muted hover:text-primary"
                }
                onClick={() => setPortfolioGroupBy(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
        {portfolio?.group_by === "step" && (
          <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
            <DataTable
              columns={STEP_COLUMNS}
              data={portfolio.items}
              getRowId={(row) => String(row.step_id)}
              isLoading={isLoadingPortfolio}
              emptyMessage="Nenhum processo ativo na carteira."
            />
            <DonutChart
              title="Ativos por fase"
              data={portfolio.items
                .filter((item) => item.active > 0)
                .map((item) => ({ label: item.step_name, value: item.active }))}
            />
          </div>
        )}
        {portfolio?.group_by === "period" && (
          <DataTable
            columns={PERIOD_COLUMNS}
            data={portfolio.items}
            getRowId={(row) => row.month}
            isLoading={isLoadingPortfolio}
            emptyMessage="Nenhum processo ativo na carteira."
          />
        )}
      </section>

      {data && (
        <div className="space-y-1">
          <BiRefreshIndicator hint={data.staleness_hint} />
          <p className="text-xs text-muted">{data.crm_warning}</p>
        </div>
      )}
    </div>
  );
}

import { useQueries, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { BarChart } from "@/components/domain/BarChart";
import { FilterBar } from "@/components/domain/FilterBar";
import type { FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { listActionGroups } from "@/features/action-groups/api";
import {
  getBiSuccessRate,
  getBiSuccessTrend,
  getBiVintage,
  type SuccessTrendPointData,
} from "@/features/reports/api";
import { BiRefreshIndicator } from "@/features/reports/BiRefreshIndicator";
import { SuccessRateCard } from "@/features/reports/SuccessRateCard";
import { SuccessTrendChart } from "@/features/reports/SuccessTrendChart";
import { VintageTable } from "@/features/reports/VintageTable";

const EMPTY_TREND: SuccessTrendPointData[] = [];

/** Aba "Safra e Qualidade" do BI (spec 075): taxa de sucesso por grupo com sparkline
 * de 24 meses, evolução mensal da taxa, volume concluído por safra e a tabela ano ×
 * estágio. A tabela vem da view (até 8 h de defasagem, sinalizada); taxa e série são
 * tempo real (a view é anual — §9.2 da 074). */
export function VintagePanel(): JSX.Element {
  const { data: actionGroups } = useQuery({
    queryKey: ["action-groups", "active"],
    queryFn: () => listActionGroups({ status: "active" }),
  });

  const filterFields = React.useMemo<FilterFieldDef[]>(
    () => [
      { key: "from_year", label: "Safra de", type: "text" },
      { key: "to_year", label: "Safra até", type: "text" },
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
  const fromYear =
    typeof values.from_year === "string" && /^\d{4}$/.test(values.from_year)
      ? Number(values.from_year)
      : undefined;
  const toYear =
    typeof values.to_year === "string" && /^\d{4}$/.test(values.to_year)
      ? Number(values.to_year)
      : undefined;
  const actionGroupId =
    typeof values.action_group_id === "string" ? values.action_group_id : undefined;

  const { data: vintage, isLoading: isLoadingVintage } = useQuery({
    queryKey: ["bi-vintage", fromYear, toYear, actionGroupId],
    queryFn: () => getBiVintage({ fromYear, toYear, actionGroupId }),
  });

  const { data: successRate, isLoading: isLoadingRate } = useQuery({
    queryKey: ["bi-success-rate", actionGroupId],
    queryFn: () => getBiSuccessRate({ actionGroupId }),
  });

  const { data: trend } = useQuery({
    queryKey: ["bi-success-trend", actionGroupId],
    queryFn: () => getBiSuccessTrend({ actionGroupId }),
  });

  // Sparkline de cada card: uma série de 24 meses por grupo (regra 6). Grupos são
  // poucos (6 padrão), então uma query por grupo é barato e o TanStack Query cacheia.
  const groups = successRate?.groups ?? [];
  const trendQueries = useQueries({
    queries: groups.map((group) => ({
      queryKey: ["bi-success-trend", group.action_group_id],
      queryFn: () => getBiSuccessTrend({ actionGroupId: group.action_group_id }),
    })),
  });

  const rateNote = successRate?.rate_note ?? "";

  return (
    <div className="space-y-4">
      <FilterBar fields={filterFields} />

      <section aria-label="Taxa de sucesso por grupo de ação" className="space-y-2">
        <h3 className="text-sm font-medium text-primary">
          Taxa de sucesso por grupo de ação — mês corrente
        </h3>
        {isLoadingRate ? (
          <div className="h-24 animate-pulse rounded bg-surface-muted" />
        ) : groups.length === 0 ? (
          <p className="text-sm text-muted">Nenhum grupo de ação cadastrado.</p>
        ) : (
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            {groups.map((group, index) => (
              <SuccessRateCard
                key={group.action_group_id}
                group={group}
                trend={trendQueries[index]?.data?.points ?? EMPTY_TREND}
                rateNote={rateNote}
              />
            ))}
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <SuccessTrendChart points={trend?.points ?? EMPTY_TREND} />
        <BarChart
          title="Concluídos por safra"
          data={(vintage?.years ?? []).map((year) => ({
            label: String(year.vintage_year),
            value: year.won + year.lost + year.settled,
          }))}
        />
      </div>

      <VintageTable years={vintage?.years ?? []} isLoading={isLoadingVintage} />

      {vintage && <BiRefreshIndicator hint={vintage.staleness_hint} />}
    </div>
  );
}

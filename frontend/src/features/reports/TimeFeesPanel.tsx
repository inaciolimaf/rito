import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { StatCard } from "@/components/domain/StatCard";
import { FilterBar } from "@/components/domain/FilterBar";
import type { FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { listActionGroups } from "@/features/action-groups/api";
import {
  getBiLostTime,
  getBiTimeFees,
  getBiTimeFeesByGroup,
  getBiTimeFeesByType,
} from "@/features/reports/api";
import { BiRefreshIndicator } from "@/features/reports/BiRefreshIndicator";
import { CycleBarChart } from "@/features/reports/CycleBarChart";
import { LostTimeCard } from "@/features/reports/LostTimeCard";
import { ProfitabilityTable } from "@/features/reports/ProfitabilityTable";
import { formatBrl } from "@/lib/money";

function formatDays(value: number | null): string {
  // Regra 2: ciclo nulo é "não sei" — "—", nunca 0d.
  return value === null ? "—" : `${value.toLocaleString("pt-BR")}d`;
}

/** Aba "Tempo e Honorários" do BI (spec 076): quanto tempo se investe e quanto valor
 * se gera por processo — média de honorários, média mensal (regras 3 e 4), os 4
 * ciclos (regra 1), tempo perdido (regra 5) e rentabilidade por tipo (regra 8). Tudo
 * vem da view bi_lawsuit_cycles (até 8 h de defasagem, sinalizada no rodapé). */
export function TimeFeesPanel(): JSX.Element {
  const { data: actionGroups } = useQuery({
    queryKey: ["action-groups", "active"],
    queryFn: () => listActionGroups({ status: "active" }),
  });

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
      { key: "from", label: "Fechado de", type: "text" },
      { key: "to", label: "Fechado até", type: "text" },
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
  // Regra 7: o filtro por resultado recalcula tudo no indicador principal.
  const outcome = typeof values.outcome === "string" ? values.outcome : undefined;
  const from = typeof values.from === "string" ? values.from : undefined;
  const to = typeof values.to === "string" ? values.to : undefined;
  const actionGroupId =
    typeof values.action_group_id === "string" ? values.action_group_id : undefined;

  const { data: timeFees, isLoading } = useQuery({
    queryKey: ["bi-time-fees", outcome, from, to, actionGroupId],
    queryFn: () => getBiTimeFees({ outcome, from, to, actionGroupId }),
  });
  const { data: byGroup } = useQuery({
    queryKey: ["bi-time-fees-by-group"],
    queryFn: () => getBiTimeFeesByGroup(),
  });
  const { data: byType, isLoading: isLoadingTypes } = useQuery({
    queryKey: ["bi-time-fees-by-type"],
    queryFn: () => getBiTimeFeesByType(),
  });
  const { data: lostTime } = useQuery({
    queryKey: ["bi-lost-time"],
    queryFn: () => getBiLostTime(),
  });

  return (
    <div className="space-y-4">
      <FilterBar fields={filterFields} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <StatCard
          label="Processos no recorte"
          value={timeFees?.lawsuits ?? 0}
          isLoading={isLoading}
        />
        <StatCard
          label="Honorários médios por processo"
          value={formatBrl(timeFees?.avg_fees ?? null)}
          isLoading={isLoading}
        />
        <StatCard
          label="Média mensal de honorários"
          value={formatBrl(timeFees?.avg_monthly_fees ?? null)}
          isLoading={isLoading}
        />
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard
          label="Prospecção (criação → fechamento)"
          value={formatDays(timeFees?.cycles.prospecting_days ?? null)}
          isLoading={isLoading}
        />
        <StatCard
          label="Produção (fechamento → trânsito)"
          value={formatDays(timeFees?.cycles.production_days ?? null)}
          isLoading={isLoading}
        />
        <StatCard
          label="Execução (trânsito → arquivamento)"
          value={formatDays(timeFees?.cycles.execution_days ?? null)}
          isLoading={isLoading}
        />
        <StatCard
          label="Rotação completa (criação → arquivamento)"
          value={formatDays(timeFees?.cycles.full_cycle_days ?? null)}
          isLoading={isLoading}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <CycleBarChart groups={byGroup?.groups ?? []} />
        <LostTimeCard data={lostTime} isLoading={isLoading} />
      </div>

      <ProfitabilityTable types={byType?.types ?? []} isLoading={isLoadingTypes} />

      {timeFees && <BiRefreshIndicator hint={timeFees.staleness_hint} />}
    </div>
  );
}

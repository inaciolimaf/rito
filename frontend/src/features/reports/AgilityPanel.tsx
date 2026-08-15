import { useQuery } from "@tanstack/react-query";

import { EmptyState } from "@/components/domain/EmptyState";
import { FilterBar } from "@/components/domain/FilterBar";
import { StatCard } from "@/components/domain/StatCard";
import type { FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { DelayedTasksCard } from "@/features/reports/DelayedTasksCard";
import { DelayedUsersCard } from "@/features/reports/DelayedUsersCard";
import { getAgilityReport, getMostDelayedReport } from "@/features/reports/api";
import { useAuth } from "@/providers/AuthProvider";

function monthStartIso(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

const FILTER_FIELDS: FilterFieldDef[] = [
  { key: "from", label: "De", type: "date" },
  { key: "to", label: "Até", type: "date" },
];

/** Painel de Agilidade (spec 071 §2) — em dia / em atraso / pendente, médias de
 * cumprimento e atraso, e as duas listas de "mais atrasados" para ADMINISTRADOR+. */
export function AgilityPanel(): JSX.Element {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMINISTRADOR" || user?.role === "GESTOR";
  const { values } = useFilters(FILTER_FIELDS);
  const from = typeof values.from === "string" ? values.from : monthStartIso();
  const to = typeof values.to === "string" ? values.to : todayIso();

  const { data, isLoading } = useQuery({
    queryKey: ["reports-agility", from, to],
    queryFn: () => getAgilityReport({ from, to }),
  });

  const { data: mostDelayed, isLoading: isLoadingMostDelayed } = useQuery({
    queryKey: ["reports-most-delayed"],
    queryFn: () => getMostDelayedReport(),
    enabled: isAdmin,
  });

  const hasData = (data?.on_time ?? 0) + (data?.late ?? 0) + (data?.pending ?? 0) > 0;

  return (
    <div className="space-y-4">
      <FilterBar fields={FILTER_FIELDS} />

      {!isLoading && !hasData ? (
        <EmptyState
          title="Sem dados no período"
          description="Nenhuma tarefa com prazo fatal ou conclusão neste intervalo."
        />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            <StatCard label="Em dia" value={data?.on_time ?? 0} isLoading={isLoading} />
            <StatCard label="Em atraso" value={data?.late ?? 0} isLoading={isLoading} />
            <StatCard label="Pendentes" value={data?.pending ?? 0} isLoading={isLoading} />
            <StatCard
              label="Dias médios p/ concluir"
              value={data?.avg_days_to_complete ?? "—"}
              isLoading={isLoading}
            />
            <StatCard
              label="Atraso médio (dias)"
              value={data?.avg_delay_days ?? "—"}
              isLoading={isLoading}
            />
          </div>
          {data && <p className="text-xs text-muted">{data.staleness_hint}</p>}
        </>
      )}

      {isAdmin && (
        <div className="grid gap-4 lg:grid-cols-2">
          <DelayedTasksCard tasks={mostDelayed?.tasks ?? []} isLoading={isLoadingMostDelayed} />
          <DelayedUsersCard users={mostDelayed?.users ?? []} isLoading={isLoadingMostDelayed} />
        </div>
      )}
    </div>
  );
}

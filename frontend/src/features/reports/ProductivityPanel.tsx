import { useQuery } from "@tanstack/react-query";

import { StatCard } from "@/components/domain/StatCard";
import { RankingTable } from "@/features/taskscore/RankingTable";
import { getProductivityReport, getProductivityWeeklyReport } from "@/features/reports/api";
import { WeeklyChart } from "@/features/reports/WeeklyChart";
import { useAuth } from "@/providers/AuthProvider";

/** Painel de Produtividade (spec 071 §2) — atribuídas/concluídas/atrasadas do mês,
 * prazo fatal em 5 dias, gráfico semanal e o ranking dos 4 critérios (spec 039). */
export function ProductivityPanel(): JSX.Element {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMINISTRADOR" || user?.role === "GESTOR";

  const { data, isLoading } = useQuery({
    queryKey: ["reports-productivity"],
    queryFn: () => getProductivityReport({}),
  });
  const { data: weekly } = useQuery({
    queryKey: ["reports-productivity-weekly"],
    queryFn: () => getProductivityWeeklyReport(),
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Atribuídas no mês" value={data?.assigned ?? 0} isLoading={isLoading} />
        <StatCard label="Concluídas no mês" value={data?.completed ?? 0} isLoading={isLoading} />
        <StatCard label="Atrasadas no mês" value={data?.late ?? 0} isLoading={isLoading} />
        <StatCard
          label="Prazo fatal em 5 dias"
          value={data?.due_in_5_days ?? 0}
          isLoading={isLoading}
        />
      </div>

      <div className="rounded border border-default bg-surface p-4">
        <h3 className="mb-3 text-sm font-medium text-primary">Semana atual (seg–sex)</h3>
        {weekly && <WeeklyChart days={weekly.days} />}
      </div>

      {isAdmin && <RankingTable />}
    </div>
  );
}

import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { BarChart, StatCard } from "@/components/domain";
import { getLawsuitStats, type LawsuitStatsCard } from "@/features/lawsuits/api";
import { GoalProgress } from "@/features/lawsuits/GoalProgress";

type Trend = "up" | "down" | "flat";

/** Rótulo de variação pronto da API (regras 1–2): delta null com valor positivo é
 * "novo", não ∞; null com valor zero é período sem movimento nos dois meses. */
function variationOf(card: LawsuitStatsCard): { label: string; trend: Trend } {
  if (card.delta_pct === null) {
    return card.value > 0
      ? { label: "novo este mês", trend: "up" }
      : { label: "sem movimento", trend: "flat" };
  }
  const trend: Trend = card.delta_pct > 0 ? "up" : card.delta_pct < 0 ? "down" : "flat";
  const sign = card.delta_pct > 0 ? "+" : "";
  return { label: `${sign}${card.delta_pct}% vs. mês anterior`, trend };
}

/** Painel de topo da listagem de processos (spec 028): cards clicáveis que levam à
 * visão correspondente (regra 8), volume por fase e meta. Recolhível (§6). */
export function LawsuitStatsPanel(): JSX.Element {
  const [collapsed, setCollapsed] = React.useState(false);
  const { data: stats } = useQuery({
    queryKey: ["lawsuits", "stats"],
    queryFn: () => getLawsuitStats(),
  });

  return (
    <section aria-label="Painel de processos" className="space-y-3">
      <button
        type="button"
        aria-expanded={!collapsed}
        className="text-sm text-accent underline"
        onClick={() => setCollapsed((current) => !current)}
      >
        {collapsed ? "Mostrar painel" : "Recolher painel"}
      </button>

      {!collapsed && stats && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <StatCard
              label="Processos ativos"
              value={stats.active.value}
              variation={variationOf(stats.active)}
              href="/lawsuits?view=active"
            />
            <StatCard
              label="Fechamentos no mês"
              value={stats.closed_this_month.value}
              variation={variationOf(stats.closed_this_month)}
              href="/lawsuits?view=closed_this_month"
            />
            <StatCard
              label="Arquivados no mês"
              value={stats.archived_this_month.value}
              variation={variationOf(stats.archived_this_month)}
              href="/lawsuits?view=archived_this_month"
            />
            <GoalProgress goal={stats.closure_goal} />
          </div>

          <div className="rounded border border-default bg-surface p-4">
            <BarChart
              title="Volume por fase"
              data={stats.volume_by_step.map((item) => ({
                label: `${item.step} (${item.pct}%)`,
                value: item.count,
              }))}
            />
          </div>
        </>
      )}
    </section>
  );
}

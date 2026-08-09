import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { StatCard } from "@/components/domain/StatCard";
import { getMyScore, getScoreChart } from "@/features/taskscore/api";
import { RankingTable } from "@/features/taskscore/RankingTable";
import { ScoreChart } from "@/features/taskscore/ScoreChart";
import { UserScoreCard } from "@/features/taskscore/UserScoreCard";
import { useAuth } from "@/providers/AuthProvider";

/** Painel de desempenho do /home (spec 039 §6, aba Desempenho): os cards do próprio
 * usuário para qualquer perfil (regra 6); o ranking completo só para ADMINISTRADOR+. */
export function TaskscorePanel(): JSX.Element {
  const { user } = useAuth();
  const [granularity, setGranularity] = React.useState<"monthly" | "daily">("monthly");
  const isAdmin = user?.role === "ADMINISTRADOR" || user?.role === "GESTOR";

  const { data: myScore } = useQuery({ queryKey: ["taskscore-me"], queryFn: () => getMyScore() });
  const { data: chart } = useQuery({
    queryKey: ["taskscore-chart", granularity],
    queryFn: () => getScoreChart(granularity),
  });

  return (
    <div className="space-y-4">
      {myScore && (
        <div className="grid gap-3 sm:grid-cols-3">
          <StatCard label="Pontos no mês" value={myScore.summary.points} />
          <StatCard label="Tarefas concluídas" value={myScore.summary.tasks_completed} />
          <StatCard
            label="Alcance da meta"
            value={myScore.summary.goal_pct === null ? "—" : `${myScore.summary.goal_pct}%`}
          />
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-2">
        {myScore && <UserScoreCard summary={myScore.summary} />}
        <div className="rounded border border-default bg-surface p-4">
          <div className="mb-2 flex justify-end gap-1" role="group" aria-label="Granularidade">
            {(["monthly", "daily"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={granularity === value}
                className={
                  granularity === value
                    ? "rounded border border-accent px-2 py-1 text-xs font-medium text-primary"
                    : "rounded border border-transparent px-2 py-1 text-xs text-muted hover:text-primary"
                }
                onClick={() => setGranularity(value)}
              >
                {value === "monthly" ? "Mensal" : "Diário"}
              </button>
            ))}
          </div>
          {chart && <ScoreChart chart={chart} />}
        </div>
      </div>

      {isAdmin && <RankingTable />}
    </div>
  );
}

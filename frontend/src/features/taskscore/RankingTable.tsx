import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { getRanking, type RankingSort } from "@/features/taskscore/api";

const SORT_OPTIONS: { value: RankingSort; label: string }[] = [
  { value: "points", label: "Pontuação" },
  { value: "volume", label: "Volume de tarefas" },
  { value: "late", label: "Tarefas atrasadas" },
  { value: "engagement", label: "Envolvimento" },
];

function formatEngagement(value: number | null): string {
  // Sem atribuídas no período → "—", não 0% (regra 4).
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

/** Ranking individual (spec 039 §6) — "Classificar por" (4 critérios, regra 4) e
 * "Período" (mês corrente ou VIDA TODA — ELTV, regra 5). Exige ADMINISTRADOR (regra 6)
 * — o painel só renderiza este componente para quem tem o perfil. */
export function RankingTable(): JSX.Element {
  const [sort, setSort] = React.useState<RankingSort>("points");
  const [period, setPeriod] = React.useState<"month" | "eltv">("month");

  const { data, isLoading } = useQuery({
    queryKey: ["taskscore-ranking", sort, period],
    queryFn: () => getRanking(sort, period === "eltv" ? "eltv" : undefined),
  });

  return (
    <section aria-label="Ranking" className="space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-muted">
          Classificar por
          <select
            className="rounded border border-default bg-surface px-2 py-1 text-sm text-primary"
            value={sort}
            onChange={(event) => setSort(event.target.value as RankingSort)}
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm text-muted">
          Período
          <select
            className="rounded border border-default bg-surface px-2 py-1 text-sm text-primary"
            value={period}
            onChange={(event) => setPeriod(event.target.value as "month" | "eltv")}
          >
            <option value="month">Mês atual</option>
            <option value="eltv">Vida toda (ELTV)</option>
          </select>
        </label>
      </div>

      <div className="overflow-x-auto rounded border border-default">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-default text-left text-muted">
              <th className="px-3 py-2 font-medium">#</th>
              <th className="px-3 py-2 font-medium">Colaborador</th>
              <th className="px-3 py-2 text-right font-medium">Pontos</th>
              <th className="px-3 py-2 text-right font-medium">Concluídas</th>
              <th className="px-3 py-2 text-right font-medium">Atrasadas</th>
              <th className="px-3 py-2 text-right font-medium">Envolvimento</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((item, index) => (
              <tr key={item.user_id} className="border-b border-default last:border-0">
                <td className="px-3 py-2 text-muted">{index + 1}</td>
                <td className="px-3 py-2 text-primary">{item.user_name}</td>
                <td className="px-3 py-2 text-right text-primary">{item.points}</td>
                <td className="px-3 py-2 text-right text-primary">{item.tasks_completed}</td>
                <td className="px-3 py-2 text-right text-primary">{item.late}</td>
                <td className="px-3 py-2 text-right text-primary">
                  {formatEngagement(item.engagement)}
                </td>
              </tr>
            ))}
            {!isLoading && (data?.items ?? []).length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-muted">
                  Nenhum colaborador no período.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

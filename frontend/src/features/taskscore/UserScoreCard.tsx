import type { ScoreSummary } from "@/features/taskscore/api";

export interface UserScoreCardProps {
  summary: ScoreSummary;
}

/** Card de desempenho do usuário (spec 039 §6): pontos do período, alcance da meta
 * com barra de progresso (sem meta → "—", regra 3) e contadores de prazo. */
export function UserScoreCard({ summary }: UserScoreCardProps): JSX.Element {
  const pct = summary.goal_pct;
  return (
    <section
      aria-label={`Desempenho de ${summary.user_name}`}
      className="flex flex-col gap-2 rounded border border-default bg-surface p-4"
    >
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-primary">{summary.user_name}</h3>
        <p className="text-2xl font-semibold text-primary">
          {summary.points}
          <span className="text-base font-normal text-muted"> pts</span>
        </p>
      </div>

      {pct === null ? (
        <p className="text-sm text-muted">Meta: —</p>
      ) : (
        <>
          <div
            className="h-2 rounded bg-surface-muted"
            role="progressbar"
            aria-valuenow={Math.min(100, pct)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Alcance da meta de pontos"
          >
            <div className="h-2 rounded bg-accent" style={{ width: `${Math.min(100, pct)}%` }} />
          </div>
          <p className="text-sm text-muted">
            {pct}% da meta ({summary.points_goal} pts)
          </p>
        </>
      )}

      <p className="text-sm text-muted">
        {summary.tasks_completed} concluídas · {summary.on_time} no prazo · {summary.late} em atraso
      </p>
    </section>
  );
}

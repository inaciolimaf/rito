import { Link } from "react-router-dom";

export interface ClosureGoal {
  target: number;
  achieved: number;
  pct: number;
}

export interface GoalProgressProps {
  goal: ClosureGoal | null;
}

/** Widget de meta de fechamentos (spec 028 §6). A meta em si só é configurável na
 * spec 039 — até lá `goal` é sempre null e o widget convida a configurar (regra 6). */
export function GoalProgress({ goal }: GoalProgressProps): JSX.Element {
  if (goal === null) {
    return (
      <div className="flex flex-col gap-1 rounded border border-default bg-surface p-4">
        <h3 className="text-sm font-medium text-primary">Meta de fechamentos</h3>
        <p className="text-sm text-muted">Nenhuma meta configurada para este mês.</p>
        <Link to="/goals" className="text-sm text-accent underline">
          Configurar meta
        </Link>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2 rounded border border-default bg-surface p-4">
      <h3 className="text-sm font-medium text-primary">Meta de fechamentos</h3>
      <p className="text-2xl font-semibold text-primary">
        {goal.achieved}
        <span className="text-base font-normal text-muted"> / {goal.target}</span>
      </p>
      <div
        className="h-2 rounded bg-surface-muted"
        role="progressbar"
        aria-valuenow={goal.pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Progresso da meta de fechamentos"
      >
        <div className="h-2 rounded bg-accent" style={{ width: `${Math.min(100, goal.pct)}%` }} />
      </div>
      <p className="text-sm text-muted">{goal.pct}% da meta do mês</p>
    </div>
  );
}

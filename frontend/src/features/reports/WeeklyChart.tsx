import type { WeeklyChartPoint } from "@/features/reports/api";

export interface WeeklyChartProps {
  days: WeeklyChartPoint[];
}

/** Gráfico semanal atribuídas × concluídas, segunda a sexta (spec 071 §6, regra 6) —
 * duas barras por dia, no mesmo estilo SVG-free do BarChart (spec 019). */
export function WeeklyChart({ days }: WeeklyChartProps): JSX.Element {
  const max = Math.max(1, ...days.flatMap((day) => [day.assigned, day.completed]));

  if (days.every((day) => day.assigned === 0 && day.completed === 0)) {
    return <p className="text-sm text-muted">Sem tarefas atribuídas ou concluídas nesta semana.</p>;
  }

  return (
    <div className="space-y-3" role="img" aria-label="Atribuídas × concluídas na semana">
      <div className="flex items-center gap-4 text-xs text-muted">
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-accent" /> Atribuídas
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-full bg-success" /> Concluídas
        </span>
      </div>
      <ul className="space-y-2">
        {days.map((day) => (
          <li key={day.day} className="flex items-center gap-2 text-sm">
            <span className="w-8 shrink-0 text-muted">{day.label}</span>
            <span className="flex flex-1 flex-col gap-0.5">
              <span className="flex items-center gap-1">
                <span className="h-2 flex-1 rounded bg-surface-muted">
                  <span
                    className="block h-2 rounded bg-accent"
                    style={{ width: `${(day.assigned / max) * 100}%` }}
                  />
                </span>
                <span className="w-6 shrink-0 text-right text-primary">{day.assigned}</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="h-2 flex-1 rounded bg-surface-muted">
                  <span
                    className="block h-2 rounded bg-success"
                    style={{ width: `${(day.completed / max) * 100}%` }}
                  />
                </span>
                <span className="w-6 shrink-0 text-right text-primary">{day.completed}</span>
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

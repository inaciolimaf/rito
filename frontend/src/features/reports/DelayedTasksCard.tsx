import { EmptyState } from "@/components/domain/EmptyState";
import type { DelayedTaskItem } from "@/features/reports/api";

export interface DelayedTasksCardProps {
  tasks: DelayedTaskItem[];
  isLoading?: boolean;
}

/** Tarefas com mais atraso (spec 071 §2) — tarefa privada nunca aparece aqui (spec 033
 * regra 8: invisível a terceiros), embora entre nos agregados de Agilidade. */
export function DelayedTasksCard({ tasks, isLoading }: DelayedTasksCardProps): JSX.Element {
  if (!isLoading && tasks.length === 0) {
    return (
      <EmptyState
        title="Nenhuma tarefa atrasada"
        description="Ninguém concluiu tarefas fora do prazo até agora."
      />
    );
  }

  return (
    <section aria-label="Tarefas com mais atraso" className="space-y-2">
      <h3 className="text-sm font-medium text-primary">Tarefas com mais atraso</h3>
      <ul className="divide-y divide-default rounded border border-default">
        {tasks.map((task) => (
          <li key={task.post_id} className="flex items-center justify-between px-3 py-2 text-sm">
            <div>
              <p className="text-primary">{task.task_type_name}</p>
              <p className="text-xs text-muted">
                {task.user_name}
                {task.lawsuit_folder ? ` · ${task.lawsuit_folder}` : ""}
              </p>
            </div>
            <span className="text-danger">{task.delay_days} dia(s)</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

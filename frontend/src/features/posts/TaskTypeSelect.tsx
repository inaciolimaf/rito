import { useQuery } from "@tanstack/react-query";

import { Label } from "@/components/ui/label";
import { listTaskTypes } from "@/features/task-types/api";

const SELECT_CLASS =
  "h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export interface TaskTypeSelectProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
}

/** Select do catálogo de tarefas (spec 031/032) — cada opção mostra a pontuação do
 * tipo ("ANÁLISE DO CASO (8 pts)"), o incentivo visível do Taskscore. */
export function TaskTypeSelect({ id, value, onChange }: TaskTypeSelectProps): JSX.Element {
  const { data } = useQuery({
    queryKey: ["task-types", "for-post-form"],
    queryFn: () => listTaskTypes({ status: "active" }),
  });
  const taskTypes = data?.items ?? [];

  return (
    <div className="space-y-1">
      <Label htmlFor={id}>Tarefa</Label>
      <select
        id={id}
        className={SELECT_CLASS}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">Selecione</option>
        {taskTypes.map((taskType) => (
          <option key={taskType.id} value={taskType.id}>
            {taskType.name} ({taskType.reward} pts)
          </option>
        ))}
      </select>
    </div>
  );
}

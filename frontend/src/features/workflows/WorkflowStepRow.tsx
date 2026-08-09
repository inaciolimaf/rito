import { ArrowDown, ArrowUp, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TaskTypeSelect } from "@/features/posts/TaskTypeSelect";

export interface WorkflowStepValue {
  task_type_id: string;
  user_id: string | null;
  days_offset: string; // "" = sem prazo (regra 4)
}

export interface WorkflowStepRowProps {
  step: WorkflowStepValue;
  index: number;
  total: number;
  userOptions: { value: string; label: string }[];
  onChange: (index: number, next: WorkflowStepValue) => void;
  onMove: (index: number, direction: -1 | 1) => void;
  onRemove: (index: number) => void;
}

const SELECT_CLASS =
  "h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/** Uma linha do editor (spec 038 §6): tipo de tarefa (obrigatório, regra 1),
 * responsável opcional (vazio = responsável do processo, regra 2) e prazo em dias
 * úteis (vazio = sem prazo, regra 4). */
export function WorkflowStepRow({
  step,
  index,
  total,
  userOptions,
  onChange,
  onMove,
  onRemove,
}: WorkflowStepRowProps): JSX.Element {
  return (
    <div
      data-testid="workflow-step-row"
      className="flex items-end gap-2 rounded border border-default p-2"
    >
      <span className="pb-2 text-sm text-muted">{index + 1}.</span>
      <div className="flex-1">
        <TaskTypeSelect
          id={`step-task-type-${index}`}
          value={step.task_type_id}
          onChange={(value) => onChange(index, { ...step, task_type_id: value })}
        />
      </div>
      <div className="w-52 space-y-1">
        <label htmlFor={`step-user-${index}`} className="text-sm font-medium">
          Responsável
        </label>
        <select
          id={`step-user-${index}`}
          className={SELECT_CLASS}
          value={step.user_id ?? ""}
          onChange={(event) => onChange(index, { ...step, user_id: event.target.value || null })}
        >
          <option value="">Responsável do processo</option>
          {userOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>
      <div className="w-32 space-y-1">
        <label htmlFor={`step-days-${index}`} className="text-sm font-medium">
          Dias úteis
        </label>
        <Input
          id={`step-days-${index}`}
          type="number"
          min={0}
          max={365}
          placeholder="Sem prazo"
          value={step.days_offset}
          onChange={(event) => onChange(index, { ...step, days_offset: event.target.value })}
        />
      </div>
      <div className="flex gap-1 pb-0.5">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={`Mover etapa ${index + 1} para cima`}
          disabled={index === 0}
          onClick={() => onMove(index, -1)}
        >
          <ArrowUp className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={`Mover etapa ${index + 1} para baixo`}
          disabled={index === total - 1}
          onClick={() => onMove(index, 1)}
        >
          <ArrowDown className="h-4 w-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={`Remover etapa ${index + 1}`}
          onClick={() => onRemove(index)}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

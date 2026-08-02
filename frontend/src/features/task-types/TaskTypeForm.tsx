import * as React from "react";
import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listSteps, type StepData } from "@/features/stages/api";
import {
  suggestTaskReward,
  type TaskComplexity,
  type TaskDuration,
} from "@/features/task-types/api";
import {
  COMPLEXITY_OPTIONS,
  DURATION_OPTIONS,
  type TaskTypeFormValues,
} from "@/features/task-types/schema";

const SELECT_CLASS =
  "h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export interface TaskTypeFormProps {
  form: UseFormReturn<TaskTypeFormValues>;
  /** Tarefa sistêmica: nome travado (regra 4) — só a pontuação muda. */
  isSystem?: boolean;
}

/** Formulário do catálogo com calculadora ao vivo (spec 031 §6): escolher
 * complexidade e duração sugere os pontos — mas o campo é editável e um valor
 * digitado manualmente prevalece sobre sugestões seguintes (regra 2). */
export function TaskTypeForm({ form, isSystem = false }: TaskTypeFormProps): JSX.Element {
  const {
    register,
    watch,
    setValue,
    formState: { errors },
  } = form;

  const [steps, setSteps] = React.useState<StepData[]>([]);
  React.useEffect(() => {
    void listSteps().then(setSteps);
  }, []);

  const complexity = watch("complexity");
  const duration = watch("duration");

  // Última sugestão aplicada — só sobrescreve o campo se o valor atual ainda é a
  // sugestão anterior (ou vazio); um valor digitado manualmente prevalece (regra 2).
  const lastSuggested = React.useRef<string | null>(null);

  React.useEffect(() => {
    if (!complexity || !duration) return;
    let cancelled = false;
    void suggestTaskReward(complexity as TaskComplexity, duration as TaskDuration).then(
      (suggestion) => {
        if (cancelled) return;
        const current = form.getValues("reward");
        if (current === "" || current === lastSuggested.current) {
          const suggested = String(suggestion.reward);
          lastSuggested.current = suggested;
          setValue("reward", suggested, { shouldDirty: true });
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [complexity, duration, form, setValue]);

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="task-type-name">Tarefa</Label>
        <Input id="task-type-name" disabled={isSystem} {...register("name")} />
        {isSystem && (
          <p className="text-sm text-muted">
            Tarefa sistêmica — o nome não pode ser alterado, só a pontuação.
          </p>
        )}
        {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="task-type-complexity">Complexidade</Label>
          <select id="task-type-complexity" className={SELECT_CLASS} {...register("complexity")}>
            <option value="">Selecione</option>
            {COMPLEXITY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="task-type-duration">Tempo médio</Label>
          <select id="task-type-duration" className={SELECT_CLASS} {...register("duration")}>
            <option value="">Selecione</option>
            {DURATION_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="task-type-reward">Pontuação</Label>
          <Input
            id="task-type-reward"
            type="number"
            min={0}
            placeholder="Sugerida pela matriz"
            {...register("reward")}
          />
          {errors.reward && <p className="text-sm text-danger">{errors.reward.message}</p>}
        </div>
        <div className="space-y-1">
          <Label htmlFor="task-type-step">Fase</Label>
          <select id="task-type-step" className={SELECT_CLASS} {...register("step_id")}>
            <option value="">Todas as fases</option>
            {steps.map((step) => (
              <option key={step.id} value={String(step.id)}>
                {step.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-primary" htmlFor="task-type-schedule">
        <input id="task-type-schedule" type="checkbox" {...register("show_in_schedule")} />
        Mostrar na agenda
      </label>
    </>
  );
}

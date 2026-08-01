import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { StepData } from "@/features/stages/api";
import type { StageFormValues } from "@/features/stages/schema";

export interface StageFormProps {
  form: UseFormReturn<StageFormValues>;
  steps: StepData[];
}

/** Nome + fase + estagnação condicional (regra 3: dias só é exigido quando a estagnação está
 * ativa) — o campo de dias fica desabilitado até o checkbox ser marcado. */
export function StageForm({ form, steps }: StageFormProps): JSX.Element {
  const {
    register,
    watch,
    formState: { errors },
  } = form;

  const enableStagnantDays = watch("enable_stagnant_days");

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="stage-name">Nome da etapa</Label>
        <Input id="stage-name" {...register("name")} />
        {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="stage-step">Fase</Label>
        <select
          id="stage-step"
          className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          {...register("step_id")}
        >
          <option value="">Selecione uma fase</option>
          {steps.map((step) => (
            <option key={step.id} value={step.id}>
              {step.name}
            </option>
          ))}
        </select>
        {errors.step_id && <p className="text-sm text-danger">{errors.step_id.message}</p>}
      </div>

      <fieldset className="space-y-1">
        <label className="flex items-center gap-2 text-sm text-primary">
          <input type="checkbox" {...register("enable_stagnant_days")} />
          Marcar como estagnado após um número de dias
        </label>

        <div className="space-y-1">
          <Label htmlFor="stage-stagnant-days">Dias para estagnação</Label>
          <Input
            id="stage-stagnant-days"
            type="number"
            min={1}
            disabled={!enableStagnantDays}
            {...register("stagnant_days")}
          />
          {errors.stagnant_days && (
            <p className="text-sm text-danger">{errors.stagnant_days.message}</p>
          )}
        </div>
      </fieldset>
    </>
  );
}

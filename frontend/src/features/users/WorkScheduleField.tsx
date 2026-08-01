import type { FieldErrors, UseFormRegister } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { UserFormValues } from "@/features/users/schema";

export interface WorkScheduleFieldProps {
  register: UseFormRegister<UserFormValues>;
  errors: FieldErrors<UserFormValues>;
  disabled?: boolean;
}

/** Jornada de trabalho (spec 012, regra 5): início, intervalo e fim — os três juntos
 * porque a validação de negócio (fim > início; intervalo < jornada total) só faz sentido
 * olhando os três ao mesmo tempo. */
export function WorkScheduleField({
  register,
  errors,
  disabled = false,
}: WorkScheduleFieldProps): JSX.Element {
  return (
    <fieldset className="grid grid-cols-3 gap-4">
      <legend className="mb-1 text-sm font-medium text-primary">Jornada de trabalho</legend>

      <div className="space-y-1">
        <Label htmlFor="workStart">Início</Label>
        <Input id="workStart" type="time" disabled={disabled} {...register("workStart")} />
        {errors.workStart && <p className="text-sm text-danger">{errors.workStart.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="workInterval">Intervalo</Label>
        <Input id="workInterval" type="time" disabled={disabled} {...register("workInterval")} />
        {errors.workInterval && (
          <p className="text-sm text-danger">{errors.workInterval.message}</p>
        )}
      </div>

      <div className="space-y-1">
        <Label htmlFor="workEnd">Fim</Label>
        <Input id="workEnd" type="time" disabled={disabled} {...register("workEnd")} />
        {errors.workEnd && <p className="text-sm text-danger">{errors.workEnd.message}</p>}
      </div>
    </fieldset>
  );
}

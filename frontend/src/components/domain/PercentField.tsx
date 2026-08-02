import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { stripNonDigits } from "@/lib/br-masks";
import { formatDecimalPtBr } from "@/lib/money";

export interface PercentFieldProps<TValues extends FieldValues> {
  control: Control<TValues>;
  name: Path<TValues>;
  label: string;
  id?: string;
}

/** Percentual 0–100 com duas casas (spec 024, regra 2). Mesma mecânica do MoneyField
 * (centésimos pt-BR na tela, ponto no valor cru), com teto de 100 na máscara — o
 * backend é quem valida de fato (422). */
export function PercentField<TValues extends FieldValues>({
  control,
  name,
  label,
  id,
}: PercentFieldProps<TValues>): JSX.Element {
  const inputId = id ?? String(name);
  return (
    <div className="space-y-1">
      <Label htmlFor={inputId}>{label}</Label>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <Input
            id={inputId}
            inputMode="numeric"
            value={formatDecimalPtBr(String(field.value ?? ""))}
            onChange={(event) => {
              const digits = stripNonDigits(event.target.value).slice(0, 5);
              const cents = digits === "" ? 0 : Math.min(parseInt(digits, 10), 10000);
              field.onChange(digits === "" ? "" : (cents / 100).toFixed(2));
            }}
            onBlur={field.onBlur}
          />
        )}
      />
    </div>
  );
}

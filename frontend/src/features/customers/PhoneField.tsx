import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatPhone, stripNonDigits } from "@/lib/br-masks";

export interface PhoneFieldProps<TValues extends FieldValues> {
  control: Control<TValues>;
  name: Path<TValues>;
  label: string;
  id: string;
}

/** Regra 4: 10 dígitos (fixo) ou 11 (celular) — a máscara alterna sozinha conforme o
 * tamanho digitado. DDI/sem DDD não têm como ser digitados aqui (o campo só aceita até 11
 * dígitos), mas o 422 do backend é quem valida de fato. */
export function PhoneField<TValues extends FieldValues>({
  control,
  name,
  label,
  id,
}: PhoneFieldProps<TValues>): JSX.Element {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <Input
            id={id}
            inputMode="numeric"
            value={formatPhone(String(field.value ?? ""))}
            onChange={(event) => {
              field.onChange(stripNonDigits(event.target.value).slice(0, 11));
            }}
            onBlur={field.onBlur}
          />
        )}
      />
    </div>
  );
}

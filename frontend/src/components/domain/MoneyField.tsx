import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { stripNonDigits } from "@/lib/br-masks";
import { digitsToDecimalRaw, formatDecimalPtBr } from "@/lib/money";

export interface MoneyFieldProps<TValues extends FieldValues> {
  control: Control<TValues>;
  name: Path<TValues>;
  label: string;
  id?: string;
}

/** Campo monetário com máscara `999.999,99` (spec 024 §6). O valor guardado no formulário
 * é o cru com ponto ("1234.56") — a máscara pt-BR é só exibição. Reutilizado por todo o
 * módulo financeiro: vive em components/domain desde o primeiro uso. */
export function MoneyField<TValues extends FieldValues>({
  control,
  name,
  label,
  id,
}: MoneyFieldProps<TValues>): JSX.Element {
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
              // 14 dígitos = NUMERIC(14,2) contando os 2 de centavos (regra 1).
              const digits = stripNonDigits(event.target.value).slice(0, 14);
              field.onChange(digitsToDecimalRaw(digits));
            }}
            onBlur={field.onBlur}
          />
        )}
      />
    </div>
  );
}

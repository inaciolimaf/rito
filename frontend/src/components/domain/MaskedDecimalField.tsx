import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDecimalPtBr } from "@/lib/money";

export interface MaskedDecimalFieldProps<TValues extends FieldValues> {
  control: Control<TValues>;
  name: Path<TValues>;
  label: string;
  id?: string;
  /** Texto digitado → valor cru com ponto ("1234.56") guardado no formulário. É a única
   * coisa que separa dinheiro de percentual: teto de dígitos e teto de valor. */
  parseInput: (typed: string) => string;
  disabled?: boolean;
}

/** Campo decimal com exibição pt-BR (vírgula) e valor cru com ponto (spec 024, regra 1).
 *
 * Extraído na spec 119 (achado C): `MoneyField` e `PercentField` compartilhavam 25 linhas
 * — a duplicação estava dentro do próprio design system. O que variava era só o parsing
 * do que foi digitado, que virou `parseInput`; a casca (label, `Controller`, máscara de
 * exibição, `inputMode`) é uma só.
 */
export function MaskedDecimalField<TValues extends FieldValues>({
  control,
  name,
  label,
  id,
  parseInput,
  disabled = false,
}: MaskedDecimalFieldProps<TValues>): JSX.Element {
  const inputId = id ?? String(name);
  return (
    <div className="space-y-1">
      <Label htmlFor={inputId}>{label}</Label>
      <Controller
        control={control}
        name={name}
        render={({ field, fieldState }) => (
          <>
            <Input
              id={inputId}
              inputMode="numeric"
              disabled={disabled}
              value={formatDecimalPtBr(String(field.value ?? ""))}
              onChange={(event) => {
                field.onChange(parseInput(event.target.value));
              }}
              onBlur={field.onBlur}
            />
            {/* Spec 138, regra 5: o campo mascarado não mostrava erro nenhum — nem o do
                Zod, nem o do servidor mapeado por `FormModal`. Um campo que recusa em
                silêncio é o mesmo "nada acontece" da spec 007, regra 7. */}
            {fieldState.error?.message && (
              <p className="text-sm text-danger">{fieldState.error.message}</p>
            )}
          </>
        )}
      />
    </div>
  );
}

import type { Control, FieldValues, Path } from "react-hook-form";

import { MaskedDecimalField } from "@/components/domain/MaskedDecimalField";
import { parsePercentInput } from "@/lib/money";

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
  return (
    <MaskedDecimalField
      control={control}
      name={name}
      label={label}
      id={id}
      parseInput={parsePercentInput}
    />
  );
}

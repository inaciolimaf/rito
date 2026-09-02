import type { Control, FieldValues, Path } from "react-hook-form";

import { MaskedDecimalField } from "@/components/domain/MaskedDecimalField";
import { parseMoneyInput } from "@/lib/money";

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
  return (
    <MaskedDecimalField
      control={control}
      name={name}
      label={label}
      id={id}
      parseInput={parseMoneyInput}
    />
  );
}

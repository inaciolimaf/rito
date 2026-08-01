import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatCpfOrCnpj, maxDigitsFor, stripNonDigits } from "@/lib/br-masks";

export interface CpfCnpjFieldProps<TValues extends FieldValues> {
  control: Control<TValues>;
  name: Path<TValues>;
  personType: "PF" | "PJ";
  label?: string;
  id?: string;
}

/** Máscara dinâmica PF/PJ (spec 018, seção 6) — CPF (999.999.999-99) para PF, CNPJ
 * (99.999.999/9999-99) para PJ. O valor no formulário fica só com dígitos (regra 3); o
 * dígito verificador real é validado pelo backend (422), não aqui. */
export function CpfCnpjField<TValues extends FieldValues>({
  control,
  name,
  personType,
  label,
  id = "identification",
}: CpfCnpjFieldProps<TValues>): JSX.Element {
  const resolvedLabel = label ?? (personType === "PJ" ? "CNPJ" : "CPF");

  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{resolvedLabel}</Label>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <Input
            id={id}
            inputMode="numeric"
            value={formatCpfOrCnpj(String(field.value ?? ""), personType)}
            onChange={(event) => {
              const digits = stripNonDigits(event.target.value).slice(0, maxDigitsFor(personType));
              field.onChange(digits);
            }}
            onBlur={field.onBlur}
          />
        )}
      />
    </div>
  );
}

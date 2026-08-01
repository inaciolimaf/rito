import * as React from "react";
import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatPostalCode, stripNonDigits } from "@/lib/br-masks";
import { lookupCep, type CepResult } from "@/lib/cep";

export interface PostalCodeFieldProps<TValues extends FieldValues> {
  control: Control<TValues>;
  name: Path<TValues>;
  onFound: (result: CepResult) => void;
  id?: string;
}

/** Busca ao completar (spec 018, seção 6) — assim que o CEP chega a 8 dígitos, dispara o
 * ViaCEP sozinho (sem esperar blur). Regra 7: fora do ar não bloqueia, só mostra um aviso —
 * os campos de endereço continuam editáveis manualmente. */
export function PostalCodeField<TValues extends FieldValues>({
  control,
  name,
  onFound,
  id = "postal_code",
}: PostalCodeFieldProps<TValues>): JSX.Element {
  const [isLookingUp, setIsLookingUp] = React.useState(false);
  const [notFound, setNotFound] = React.useState(false);

  async function triggerLookup(digits: string): Promise<void> {
    if (digits.length !== 8) return;
    setIsLookingUp(true);
    setNotFound(false);
    try {
      const result = await lookupCep(digits);
      if (result) {
        onFound(result);
      } else {
        setNotFound(true);
      }
    } finally {
      setIsLookingUp(false);
    }
  }

  return (
    <div className="space-y-1">
      <Label htmlFor={id}>CEP</Label>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <Input
            id={id}
            inputMode="numeric"
            value={formatPostalCode(String(field.value ?? ""))}
            onChange={(event) => {
              const digits = stripNonDigits(event.target.value).slice(0, 8);
              field.onChange(digits);
              void triggerLookup(digits);
            }}
            onBlur={field.onBlur}
          />
        )}
      />
      {isLookingUp && <p className="text-sm text-muted">Buscando endereço...</p>}
      {notFound && (
        <p className="text-sm text-muted">
          Não foi possível buscar o endereço — preencha manualmente.
        </p>
      )}
    </div>
  );
}

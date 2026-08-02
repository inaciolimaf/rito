import * as React from "react";
import { Controller, type Control, type FieldValues, type Path } from "react-hook-form";

import type { ProcessNumberValidation } from "@/features/lawsuits/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { stripNonDigits } from "@/lib/br-masks";
import { formatCnj } from "@/lib/cnj";

export interface InferredCourtOption {
  id: string;
  code: string;
  name: string;
}

export interface ProcessNumberFieldProps<TValues extends FieldValues> {
  control: Control<TValues>;
  name: Path<TValues>;
  label?: string;
  id?: string;
  /** Validação real acontece no backend (DV/ano/segmento nunca são duplicados no cliente). */
  onValidate: (rawDigits: string) => Promise<ProcessNumberValidation>;
  onCourtInferred?: (court: InferredCourtOption) => void;
}

/** Número do processo (spec 025 §6): máscara `9999999-99.9999.9.99.9999`, validação em
 * tempo real ao completar 20 dígitos, sugestão de tribunal inferido e botão de colar que
 * normaliza qualquer formato (regra 1). O valor no formulário fica só com dígitos. */
export function ProcessNumberField<TValues extends FieldValues>({
  control,
  name,
  label = "Número do processo",
  id = "process_number",
  onValidate,
  onCourtInferred,
}: ProcessNumberFieldProps<TValues>): JSX.Element {
  const [error, setError] = React.useState<string | null>(null);
  const [hint, setHint] = React.useState<string | null>(null);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  function scheduleValidation(rawDigits: string): void {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    setError(null);
    setHint(null);
    if (rawDigits.length !== 20) return;
    debounceRef.current = setTimeout(() => {
      void onValidate(rawDigits).then((result) => {
        if (!result.valid) {
          setError(result.error ?? "Número inválido.");
          return;
        }
        if (result.inferred_court) {
          setHint(
            `Tribunal sugerido: ${result.inferred_court.code} — ${result.inferred_court.name}`,
          );
          onCourtInferred?.({
            id: String(result.inferred_court.id),
            code: result.inferred_court.code,
            name: result.inferred_court.name,
          });
        }
      });
    }, 300);
  }

  React.useEffect(
    () => () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    },
    [],
  );

  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Controller
        control={control}
        name={name}
        render={({ field }) => (
          <div className="flex gap-2">
            <Input
              id={id}
              inputMode="numeric"
              placeholder="0000000-00.0000.0.00.0000"
              value={formatCnj(String(field.value ?? ""))}
              onChange={(event) => {
                const digits = stripNonDigits(event.target.value).slice(0, 20);
                field.onChange(digits);
                scheduleValidation(digits);
              }}
              onBlur={field.onBlur}
            />
            <button
              type="button"
              aria-label="Colar número do processo"
              className="shrink-0 rounded border border-default bg-surface px-2 text-xs text-muted hover:text-primary"
              onClick={() => {
                void navigator.clipboard.readText().then((text) => {
                  const digits = stripNonDigits(text).slice(0, 20);
                  field.onChange(digits);
                  scheduleValidation(digits);
                });
              }}
            >
              Colar
            </button>
          </div>
        )}
      />
      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}
      {hint && <p className="text-sm text-muted">{hint}</p>}
    </div>
  );
}

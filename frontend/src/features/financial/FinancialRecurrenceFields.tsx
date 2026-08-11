import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { FinancialRecurrence } from "@/features/financial/api";
import type { TransactionFormValues } from "@/features/financial/schema";

export interface FinancialRecurrenceFieldsProps {
  form: UseFormReturn<TransactionFormValues>;
}

const RECURRENCE_LABELS: Record<FinancialRecurrence, string> = {
  MENSAL: "Mensal",
  BIMESTRAL: "Bimestral",
  TRIMESTRAL: "Trimestral",
  SEMESTRAL: "Semestral",
  ANUAL: "Anual",
};

const SELECT_CLASS =
  "h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/** Regra 4/5/12 (spec 057): só a primeira ocorrência nasce aqui — o worker mensal gera o
 * resto. Sem data-fim a recorrência é indefinida (regra 5), então "até" é opcional. */
export function FinancialRecurrenceFields({ form }: FinancialRecurrenceFieldsProps): JSX.Element {
  const { register } = form;

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="space-y-1">
        <Label htmlFor="recurrence-period">Periodicidade</Label>
        <select id="recurrence-period" className={SELECT_CLASS} {...register("recurrencePeriod")}>
          {Object.entries(RECURRENCE_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="recurrence-until">Até (opcional)</Label>
        <Input id="recurrence-until" type="date" {...register("recurrenceUntilDate")} />
      </div>
    </div>
  );
}

import type { UseFormReturn } from "react-hook-form";

import { Label } from "@/components/ui/label";
import type { LawsuitFormValues } from "@/features/lawsuits/schema";

const SELECT_CLASS =
  "h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export const CONTINGENCY_LABELS: Record<string, string> = {
  PROVAVEL: "Provável",
  POSSIVEL: "Possível",
  REMOTA: "Remota",
};

export interface ContingencySelectProps {
  form: UseFormReturn<LawsuitFormValues>;
}

/** Contingenciamento (spec 024, regra 6): opcional, sem cálculo aqui — insumo de BI. */
export function ContingencySelect({ form }: ContingencySelectProps): JSX.Element {
  return (
    <div className="space-y-1">
      <Label htmlFor="contingency">Contingenciamento</Label>
      <select id="contingency" className={SELECT_CLASS} {...form.register("contingency")}>
        <option value="">Selecione</option>
        {Object.entries(CONTINGENCY_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
    </div>
  );
}

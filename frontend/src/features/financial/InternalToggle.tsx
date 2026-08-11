import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { TransactionFormValues } from "@/features/financial/schema";

export interface InternalToggleProps {
  form: UseFormReturn<TransactionFormValues>;
}

/** Regra 1/2 (spec 058): marca o lançamento como "só controle" — explica inline que ele
 * some do saldo/caixa mas continua visível na listagem e no painel do processo, pra não
 * parecer um bug quando o número não bater com o extrato. */
export function InternalToggle({ form }: InternalToggleProps): JSX.Element {
  const { register, watch } = form;
  const isInternal = watch("is_internal");

  return (
    <div className="space-y-2 rounded border border-default p-3">
      <label className="flex items-center gap-2 text-sm text-primary">
        <input type="checkbox" {...register("is_internal")} />
        Lançamento interno (só controle)
      </label>
      <p className="text-xs text-muted">
        Não entra no saldo da conta, no fluxo de caixa nem no DRE — fica visível na listagem e no
        painel do processo só como informação de gestão (ex.: honorário a combinar, provisão).
      </p>
      {isInternal && (
        <div className="space-y-1">
          <Label htmlFor="internal-note">Nota interna (opcional)</Label>
          <Input id="internal-note" {...register("internal_note")} />
        </div>
      )}
    </div>
  );
}

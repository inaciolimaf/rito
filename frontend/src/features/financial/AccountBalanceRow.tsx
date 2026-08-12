import type { AccountBalanceItem } from "@/features/financial/api";
import { formatBrl } from "@/lib/money";

export interface AccountBalanceRowProps {
  item: AccountBalanceItem;
}

/** Regra 7 (spec 059): cartão de crédito mostra a fatura do ciclo, nunca "saldo".
 * Regra 10: negativo em vermelho — sem sinal duplicado (só `formatBrl`, sem `-` manual). */
export function AccountBalanceRow({ item }: AccountBalanceRowProps): JSX.Element {
  const isNegative = item.balance < 0;
  return (
    <div className="flex items-center justify-between rounded border border-default bg-surface px-3 py-2">
      <div>
        <p className="text-sm font-medium text-primary">{item.name}</p>
        <p className="text-xs text-muted">{item.is_invoice ? "Fatura do ciclo" : "Saldo"}</p>
      </div>
      <span className={`text-sm font-semibold ${isNegative ? "text-danger" : "text-primary"}`}>
        {formatBrl(item.balance)}
      </span>
    </div>
  );
}

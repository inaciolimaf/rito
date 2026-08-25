import type { BiCacData } from "@/features/reports/api";
import { formatBrl } from "@/lib/money";

export interface CacCardProps {
  data: BiCacData | undefined;
  isLoading?: boolean;
}

/** CAC do mês (spec 077, regra 1): despesas de marketing e comercial (grupo DRE 8) ÷
 * clientes novos. Regras 8 e 9: mês sem marketing ou sem cliente novo → "—", nunca
 * zero nem infinito. */
export function CacCard({ data, isLoading = false }: CacCardProps): JSX.Element {
  return (
    <div className="flex flex-col gap-1 rounded border border-default bg-surface p-4">
      <span className="text-sm text-muted">CAC — custo de aquisição de cliente</span>
      {isLoading ? (
        <div className="h-8 w-16 animate-pulse rounded bg-surface-muted" />
      ) : !data ? (
        <span className="text-2xl font-semibold text-primary">—</span>
      ) : (
        <>
          <span className="text-2xl font-semibold text-primary">
            {data.cac === null ? "—" : formatBrl(data.cac)}
          </span>
          <span className="text-xs text-muted">
            {formatBrl(data.marketing_cost)} de marketing · {data.new_customers}{" "}
            {data.new_customers === 1 ? "cliente novo" : "clientes novos"}
          </span>
        </>
      )}
    </div>
  );
}

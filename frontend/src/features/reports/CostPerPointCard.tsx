import type { BiCostPerPointData } from "@/features/reports/api";
import { formatBrl } from "@/lib/money";

export interface CostPerPointCardProps {
  data: BiCostPerPointData | undefined;
  isLoading?: boolean;
}

/** Custo por ponto do mês (spec 077, regra 2): custo fixo (grupos DRE 2, 3, 5 e 7) ÷
 * pontos do Taskscore concluídos — a métrica que traduz esforço em dinheiro. Regra 8:
 * mês sem pontos → "—", nunca infinito. */
export function CostPerPointCard({ data, isLoading = false }: CostPerPointCardProps): JSX.Element {
  return (
    <div className="flex flex-col gap-1 rounded border border-default bg-surface p-4">
      <span className="text-sm text-muted">Custo por ponto (Taskscore)</span>
      {isLoading ? (
        <div className="h-8 w-16 animate-pulse rounded bg-surface-muted" />
      ) : !data ? (
        <span className="text-2xl font-semibold text-primary">—</span>
      ) : (
        <>
          <span className="text-2xl font-semibold text-primary">
            {data.cost_per_point === null ? "—" : formatBrl(data.cost_per_point)}
          </span>
          <span className="text-xs text-muted">
            {formatBrl(data.fixed_cost)} de custo fixo · {data.points}{" "}
            {data.points === 1 ? "ponto" : "pontos"}
          </span>
        </>
      )}
    </div>
  );
}

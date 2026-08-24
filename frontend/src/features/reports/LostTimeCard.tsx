import type { BiLostTimeData } from "@/features/reports/api";

export interface LostTimeCardProps {
  data: BiLostTimeData | undefined;
  isLoading?: boolean;
}

function formatMonths(value: number): string {
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

/** Tempo perdido (spec 076, regra 5): meses consumidos por processos sem nenhuma
 * receita paga e com rotação completa maior que zero — processo que ocupou a equipe
 * e não gerou honorário. */
export function LostTimeCard({ data, isLoading = false }: LostTimeCardProps): JSX.Element {
  if (isLoading || data === undefined) {
    return (
      <div className="flex flex-col gap-2 rounded border border-default bg-surface p-4">
        <div className="h-4 w-24 animate-pulse rounded bg-surface-muted" />
        <div className="h-8 w-16 animate-pulse rounded bg-surface-muted" />
      </div>
    );
  }
  return (
    <section
      aria-label="Tempo perdido"
      className="flex flex-col gap-1 rounded border border-default bg-surface p-4"
    >
      <span className="text-sm text-muted">Tempo perdido</span>
      <span className="text-2xl font-semibold text-primary">
        {formatMonths(data.lost_months)} meses
      </span>
      <span className="text-xs text-muted">
        {data.zero_revenue_lawsuits} {data.zero_revenue_lawsuits === 1 ? "processo" : "processos"}{" "}
        sem receita paga
      </span>
    </section>
  );
}

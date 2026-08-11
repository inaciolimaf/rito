import { BarChart } from "@/components/domain/BarChart";
import { StatCard } from "@/components/domain/StatCard";
import type { PublicationMetrics } from "@/features/integrations/api";

/** Métricas de captura (spec 049, §7) — publicações por dia/tribunal e a taxa
 * de vínculo automático que dispara o aviso da regra 8. */
export function CaptureMetricsChart({ metrics }: { metrics: PublicationMetrics }): JSX.Element {
  const ratePercent =
    metrics.auto_link_rate === null ? "—" : `${Math.round(metrics.auto_link_rate * 100)}%`;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label={`Publicações (${metrics.period_days} dias)`} value={metrics.total} />
        <StatCard label="Vinculadas automaticamente" value={metrics.auto_linked} />
        <StatCard label="Taxa de vínculo automático" value={ratePercent} />
      </div>
      <BarChart
        title="Publicações por dia"
        data={Object.entries(metrics.per_day).map(([day, count]) => ({ label: day, value: count }))}
      />
      <BarChart
        title="Publicações por tribunal"
        data={Object.entries(metrics.per_court).map(([court, count]) => ({
          label: court,
          value: count,
        }))}
      />
    </div>
  );
}

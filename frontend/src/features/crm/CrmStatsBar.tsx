import { StatCard } from "@/components/domain/StatCard";
import type { CrmStats } from "@/features/crm/api";
import { formatBrl } from "@/lib/money";

/** Cards de topo do CRM (spec 052 §2/§5) — reaproveita `StatCard` (spec 007). */
export function CrmStatsBar({
  stats,
  isLoading,
}: {
  stats: CrmStats | undefined;
  isLoading: boolean;
}): JSX.Element {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard label="Processos" value={stats?.total_lawsuits ?? 0} isLoading={isLoading} />
      <StatCard
        label="Recebidos no mês"
        value={stats?.received_this_month ?? 0}
        isLoading={isLoading}
      />
      <StatCard
        label="Valor total"
        value={formatBrl(stats?.total_value ?? null)}
        isLoading={isLoading}
      />
      <StatCard
        label="Estagnados"
        value={stats?.stagnant_count ?? 0}
        isLoading={isLoading}
        variation={
          stats && stats.stagnant_count > 0
            ? { label: formatBrl(stats.stagnant_value), trend: "down" }
            : null
        }
      />
    </div>
  );
}

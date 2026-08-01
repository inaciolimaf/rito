import { useQuery } from "@tanstack/react-query";

import { BarChart, DonutChart, StatCard } from "@/components/domain";
import { getCustomerStats } from "@/features/customers/api";

/** Dashboard de Contatos (ADVBOX §4.5): cards + 3 gráficos (spec 019, seção 2). */
export function CustomerStatsPanel(): JSX.Element | null {
  const { data: stats } = useQuery({
    queryKey: ["customers", "stats"],
    queryFn: getCustomerStats,
  });

  if (!stats) return null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Contatos cadastrados" value={stats.total} />
        <StatCard
          label="Variação vs mês anterior"
          value={`${stats.variation_vs_last_month >= 0 ? "+" : ""}${stats.variation_vs_last_month}%`}
        />
        <StatCard label="Com processo ativo" value={stats.with_active_lawsuit} />
        <StatCard label="Sem processo ativo" value={stats.without_active_lawsuit} />
      </div>

      <div className="grid grid-cols-1 gap-6 rounded border border-default bg-surface p-4 md:grid-cols-3">
        <DonutChart
          title="Top Origens"
          data={stats.top_origins.map((item) => ({ label: item.name, value: item.count }))}
        />
        <BarChart
          title="Faixa etária"
          data={stats.age_ranges.map((item) => ({ label: item.name, value: item.count }))}
        />
        <BarChart
          title="Top Profissões"
          data={stats.top_occupations.map((item) => ({ label: item.name, value: item.count }))}
        />
      </div>
    </div>
  );
}

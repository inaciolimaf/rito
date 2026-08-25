import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { DataTable } from "@/components/domain/DataTable";
import { StatCard } from "@/components/domain/StatCard";
import type { DataTableColumn } from "@/components/domain/types";
import { getAiUsage, type UsageGroupData } from "@/features/ai/api";

type GroupBy = "feature" | "model" | "status";

function formatUsd(value: number): string {
  return `US$ ${value.toFixed(4)}`;
}

const COLUMNS: DataTableColumn<UsageGroupData>[] = [
  { id: "key", header: "Chave", cell: (row) => row.key },
  { id: "calls", header: "Chamadas", cell: (row) => row.calls },
  { id: "tokens", header: "Tokens", cell: (row) => row.prompt_tokens + row.completion_tokens },
  { id: "cost", header: "Custo", cell: (row) => formatUsd(row.cost_usd) },
  { id: "errors", header: "Erros", cell: (row) => row.errors },
];

/** Consumo de IA (spec 081 §7): custo por feature, modelo ou situação. */
export function AiUsagePanel(): JSX.Element {
  const [groupBy, setGroupBy] = React.useState<GroupBy>("feature");
  const { data, isLoading } = useQuery({
    queryKey: ["ai-usage", groupBy],
    queryFn: () => getAiUsage(groupBy),
  });

  return (
    <section className="space-y-3" aria-label="Consumo de IA">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-primary">Consumo</h2>
        <select
          aria-label="Agrupar consumo por"
          className="rounded border border-default bg-surface p-1 text-xs"
          value={groupBy}
          onChange={(event) => setGroupBy(event.target.value as GroupBy)}
        >
          <option value="feature">Por feature</option>
          <option value="model">Por modelo</option>
          <option value="status">Por situação</option>
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatCard label="Chamadas" value={data?.totals.calls ?? 0} isLoading={isLoading} />
        <StatCard
          label="Custo total"
          value={formatUsd(data?.totals.cost_usd ?? 0)}
          isLoading={isLoading}
        />
        <StatCard label="Erros" value={data?.totals.errors ?? 0} isLoading={isLoading} />
        <StatCard
          label="Latência média"
          value={data?.totals.avg_latency_ms ? `${data.totals.avg_latency_ms} ms` : "—"}
          isLoading={isLoading}
        />
      </div>

      <DataTable
        columns={COLUMNS}
        data={data?.items ?? []}
        getRowId={(row) => row.key}
        isLoading={isLoading}
        emptyMessage="Nenhuma chamada de IA registrada ainda."
      />
    </section>
  );
}

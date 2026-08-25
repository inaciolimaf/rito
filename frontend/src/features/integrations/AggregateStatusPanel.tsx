import { useQuery } from "@tanstack/react-query";

import { DataTable } from "@/components/domain/DataTable";
import type { DataTableColumn } from "@/components/domain/types";
import { getAggregateStatus } from "@/features/integrations/api";
import type { AggregateStatusItem } from "@/features/integrations/api";
import { RefreshButton } from "@/features/integrations/RefreshButton";
import { StalenessIndicator } from "@/features/integrations/StalenessIndicator";

export interface AggregateStatusPanelProps {
  canRefresh: boolean;
}

function formatInterval(seconds: number): string {
  if (seconds % 3600 === 0) return `${seconds / 3600} h`;
  return `${Math.round(seconds / 60)} min`;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** Painel de status dos agregados (spec 078, §6): todas as views materializadas do
 * registry com defasagem (regra 6), último erro e refresh manual com throttle
 * (regra 8 — só GESTOR, `canRefresh`). */
export function AggregateStatusPanel({ canRefresh }: AggregateStatusPanelProps): JSX.Element {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["aggregates", "status"],
    queryFn: getAggregateStatus,
  });

  const columns: DataTableColumn<AggregateStatusItem>[] = [
    {
      id: "name",
      header: "Agregado",
      cell: (row) => (
        <span>
          <span className="block font-medium text-primary">{row.name}</span>
          <span className="block text-xs text-muted">{row.description}</span>
        </span>
      ),
    },
    {
      id: "interval",
      header: "Intervalo",
      cell: (row) => formatInterval(row.refresh_interval_seconds),
    },
    {
      id: "staleness",
      header: "Atualização",
      cell: (row) => <StalenessIndicator computedAt={row.computed_at} isStale={row.is_stale} />,
    },
    {
      id: "duration",
      header: "Duração",
      cell: (row) => formatDuration(row.last_refresh_duration_ms),
    },
    {
      id: "error",
      header: "Último erro",
      cell: (row) =>
        row.last_error === null ? (
          "—"
        ) : (
          <span className="text-xs text-danger" title={row.last_error}>
            {row.last_error.length > 60 ? `${row.last_error.slice(0, 60)}…` : row.last_error}
          </span>
        ),
    },
  ];

  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold text-primary">Agregados (views materializadas)</h2>
      <DataTable
        columns={columns}
        data={data?.items ?? []}
        getRowId={(row) => row.name}
        isLoading={isLoading}
        error={error instanceof Error ? error.message : null}
        emptyMessage="Nenhum agregado registrado."
        rowActions={
          canRefresh
            ? (row) => <RefreshButton name={row.name} onRefreshed={() => void refetch()} />
            : undefined
        }
      />
    </section>
  );
}

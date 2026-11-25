import { useQuery } from "@tanstack/react-query";

import { QueryStateGate } from "@/components/domain/QueryStateGate";
import { getTermHealth } from "@/features/integrations/api";
import { TermStatusBadge } from "@/features/monitored-terms/TermStatusBadge";
import { formatBrDateTime } from "@/lib/format";

/** Card de saúde do termo (spec 049 §6) — status atual e falhas consecutivas;
 * o histórico completo de execuções continua no `SyncRunsTable` (spec 043/044),
 * ao lado, sem duplicar. */
export function TermHealthCard({ termId }: { termId: string }): JSX.Element {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["monitored-terms", termId, "health"],
    queryFn: () => getTermHealth(termId),
  });

  return (
    <QueryStateGate
      isLoading={isLoading}
      error={error}
      data={data}
      loadingLabel="Carregando saúde do termo…"
      className=""
      onRetry={() => void refetch()}
    >
      {(health) => (
        <div className="flex flex-wrap items-center gap-4 rounded border border-default bg-surface p-3 text-sm">
          <TermStatusBadge status={health.status} />
          <span>
            Falhas seguidas:{" "}
            <span className={health.consecutive_failures > 0 ? "font-medium text-danger" : ""}>
              {health.consecutive_failures}
            </span>
          </span>
          <span>Última sincronização: {formatBrDateTime(health.last_sync_at)}</span>
          <span>Último sucesso: {formatBrDateTime(health.last_success_at)}</span>
          <span>Próxima: {formatBrDateTime(health.next_sync_at)}</span>
        </div>
      )}
    </QueryStateGate>
  );
}

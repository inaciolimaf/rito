import { useQuery } from "@tanstack/react-query";

import { getTermHealth } from "@/features/integrations/api";
import { TermStatusBadge } from "@/features/monitored-terms/TermStatusBadge";

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("pt-BR");
}

/** Card de saúde do termo (spec 049 §6) — status atual e falhas consecutivas;
 * o histórico completo de execuções continua no `SyncRunsTable` (spec 043/044),
 * ao lado, sem duplicar. */
export function TermHealthCard({ termId }: { termId: string }): JSX.Element {
  const { data, isLoading } = useQuery({
    queryKey: ["monitored-terms", termId, "health"],
    queryFn: () => getTermHealth(termId),
  });

  if (isLoading || !data) {
    return <p className="text-sm text-muted">Carregando…</p>;
  }

  return (
    <div className="flex flex-wrap items-center gap-4 rounded border border-default bg-surface p-3 text-sm">
      <TermStatusBadge status={data.status} />
      <span>
        Falhas seguidas:{" "}
        <span className={data.consecutive_failures > 0 ? "font-medium text-danger" : ""}>
          {data.consecutive_failures}
        </span>
      </span>
      <span>Última sincronização: {formatDateTime(data.last_sync_at)}</span>
      <span>Último sucesso: {formatDateTime(data.last_success_at)}</span>
      <span>Próxima: {formatDateTime(data.next_sync_at)}</span>
    </div>
  );
}

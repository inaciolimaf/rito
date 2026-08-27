import { useQuery } from "@tanstack/react-query";

import { listRuns } from "@/features/automations/api";
import { ACTION_LABELS, STATUS_LABELS } from "@/features/automations/labels";

export interface RunsTimelineProps {
  automationId: string;
}

/** Histórico de execuções (spec 092 §6).
 *
 * O passo PULADO aparece igual ao executado, com a condição que o pulou — é essa linha
 * que responde "por que a tarefa não foi criada?", que é a pergunta que chega ao
 * suporte. Esconder o pulo deixaria a automação parecendo quebrada. */
export function RunsTimeline({ automationId }: RunsTimelineProps): JSX.Element {
  const { data, isLoading } = useQuery({
    queryKey: ["automation-runs", automationId],
    queryFn: () => listRuns(automationId),
  });

  if (isLoading) return <p className="text-sm text-muted">Carregando execuções…</p>;
  const items = data?.items ?? [];
  if (items.length === 0) {
    return <p className="text-sm text-muted">Esta automação ainda não rodou nenhuma vez.</p>;
  }

  return (
    <ul className="space-y-3" aria-label="Execuções">
      {items.map((run) => (
        <li key={run.id} className="rounded border border-default p-3">
          <div className="flex items-center justify-between text-sm">
            <span>{new Date(run.started_at).toLocaleString("pt-BR")}</span>
            <span className="text-muted">{STATUS_LABELS[run.status] ?? run.status}</span>
          </div>
          {run.error && <p className="mt-1 text-xs text-danger">{run.error}</p>}
          <ol className="mt-2 space-y-1">
            {run.steps.map((passo) => (
              <li key={passo.position} className="text-xs text-muted">
                {passo.position + 1}. {ACTION_LABELS[passo.action_kind]} —{" "}
                {STATUS_LABELS[passo.status] ?? passo.status}
                {passo.status === "skipped" && " (condição não satisfeita)"}
              </li>
            ))}
          </ol>
        </li>
      ))}
    </ul>
  );
}

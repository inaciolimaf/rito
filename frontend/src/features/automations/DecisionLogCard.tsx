import type { DecisionData } from "@/features/automations/api";

export interface DecisionLogCardProps {
  decision: DecisionData;
}

/** O raciocínio de uma decisão (spec 094, regra 4).
 *
 * O card mostra o raciocínio em destaque, não o ramo: o ramo a pessoa já vê no histórico
 * da execução. O que ela não tem de outro jeito é o PORQUÊ — e é essa a pergunta que
 * chega seis semanas depois. */
export function DecisionLogCard({ decision }: DecisionLogCardProps): JSX.Element {
  return (
    <article className="space-y-1 rounded border border-default p-3" aria-label="Decisão">
      <div className="flex items-center justify-between text-xs text-muted">
        <span>{new Date(decision.created_at).toLocaleString("pt-BR")}</span>
        <span>
          {decision.model}
          {decision.confidence !== null && ` · confiança ${Math.round(decision.confidence * 100)}%`}
        </span>
      </div>
      <p className="text-sm">
        <strong>{decision.question}</strong>
      </p>
      <p className="text-sm">
        Ramo escolhido: <strong>{decision.chosen_branch ?? "—"}</strong>
      </p>
      <p className="text-sm text-muted">{decision.reasoning}</p>
      {decision.fell_back && (
        <p className="rounded border border-warning bg-warning/10 p-2 text-xs">
          A IA não decidiu: {decision.fallback_reason}
        </p>
      )}
    </article>
  );
}

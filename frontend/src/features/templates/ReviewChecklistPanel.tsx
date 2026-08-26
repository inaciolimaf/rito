import { AlertTriangle, CheckCircle2, CircleHelp, XCircle } from "lucide-react";

import type { ReviewItem } from "@/features/templates/editorAi";

const STATUS = {
  ok: { icon: CheckCircle2, className: "text-success", label: "Tudo certo" },
  atencao: { icon: AlertTriangle, className: "text-warning", label: "Atenção" },
  problema: { icon: XCircle, className: "text-danger", label: "Problema" },
  nao_avaliado: { icon: CircleHelp, className: "text-muted", label: "Não avaliado" },
} as const;

export interface ReviewChecklistPanelProps {
  items: ReviewItem[];
  isLoading?: boolean;
}

/** Checklist da revisão (spec 088, regras 5 e 6).
 *
 * O painel aponta e não oferece "corrigir tudo": corrigir por cima do texto de alguém
 * é o oposto de revisar. Cada item tem status e observação; o que fazer é decisão de
 * quem escreveu. */
export function ReviewChecklistPanel({
  items,
  isLoading = false,
}: ReviewChecklistPanelProps): JSX.Element {
  if (isLoading) {
    return <div className="h-24 animate-pulse rounded bg-surface-muted" />;
  }
  return (
    <section
      data-testid="review-checklist"
      aria-label="Revisão da peça"
      className="space-y-2 rounded border border-default bg-surface p-3"
    >
      <p className="text-xs text-muted">
        A revisão não altera o documento — as correções continuam sendo suas.
      </p>
      <ul className="space-y-2">
        {items.map((item) => {
          const status = STATUS[item.status] ?? STATUS.nao_avaliado;
          const Icon = status.icon;
          return (
            <li key={item.topic} data-testid={`review-${item.topic}`} className="flex gap-2">
              <Icon aria-hidden className={`mt-0.5 size-4 shrink-0 ${status.className}`} />
              <div className="text-sm">
                <p className="font-medium text-primary">
                  {item.label}
                  <span className={`ml-2 text-xs ${status.className}`}>{status.label}</span>
                </p>
                <p className="text-muted">{item.note}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

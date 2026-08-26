import * as React from "react";

import { Button } from "@/components/ui/button";
import { DeadlineReviewField } from "@/features/publications/DeadlineReviewField";
import type { PublicationAnalysisData, ReviewPayload } from "@/features/publications/analysis";

const ACT_TYPE_LABELS: Record<string, string> = {
  sentenca: "Sentença",
  despacho: "Despacho",
  decisao: "Decisão",
  intimacao_prazo: "Intimação com prazo",
  audiencia: "Audiência",
  recurso: "Recurso",
  pericia: "Perícia",
};

export interface PublicationAnalysisCardProps {
  analysis: PublicationAnalysisData | null;
  isAnalyzing?: boolean;
  onAnalyze: () => void;
  onReview: (payload: ReviewPayload) => Promise<unknown>;
}

/** O que a IA leu na intimação (spec 086 §6): resumo, tipo de ato, prazo e o raciocínio.
 *
 * O inteiro teor continua ao lado, sempre (regra 6) — este card resume, não substitui. */
export function PublicationAnalysisCard({
  analysis,
  isAnalyzing = false,
  onAnalyze,
  onReview,
}: PublicationAnalysisCardProps): JSX.Element {
  const [deadline, setDeadline] = React.useState("");
  const [saving, setSaving] = React.useState(false);

  if (analysis === null) {
    return (
      <section className="space-y-2 rounded border border-default bg-surface p-4">
        <p className="text-sm text-muted">Esta intimação ainda não foi analisada pela IA.</p>
        <Button type="button" onClick={onAnalyze} disabled={isAnalyzing}>
          {isAnalyzing ? "Analisando…" : "Analisar com IA"}
        </Button>
      </section>
    );
  }

  const revisada = analysis.reviewed_at !== null;
  return (
    <section
      data-testid="publication-analysis"
      aria-label="Análise da intimação"
      className="space-y-3 rounded border border-default bg-surface p-4"
    >
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium text-primary">Leitura da IA</h3>
        {analysis.act_type && (
          <span className="rounded bg-surface-muted px-2 py-0.5 text-xs text-muted">
            {ACT_TYPE_LABELS[analysis.act_type] ?? analysis.act_type}
          </span>
        )}
        {/* A confiança aparece uma vez só, colada no campo de prazo — que é onde a
            decisão acontece (ver DeadlineReviewField). */}
        <span className="ml-auto text-xs text-muted">{analysis.model}</span>
      </header>

      <p className="whitespace-pre-wrap text-sm text-primary">{analysis.summary}</p>

      {analysis.requires_action ? (
        revisada ? (
          <p className="text-sm text-success" role="status">
            Prazo confirmado por uma pessoa
            {analysis.deadline_date
              ? ` em ${new Date(`${analysis.deadline_date}T12:00:00`).toLocaleDateString("pt-BR")}`
              : ""}
            .
          </p>
        ) : (
          <>
            <DeadlineReviewField
              suggested={analysis.deadline_date}
              confidence={analysis.deadline_confidence}
              reasoning={analysis.reasoning}
              shouldPrefill={analysis.should_prefill_deadline}
              value={deadline}
              onChange={setDeadline}
            />
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                disabled={saving}
                onClick={async () => {
                  setSaving(true);
                  try {
                    await onReview({ approved: false });
                  } finally {
                    setSaving(false);
                  }
                }}
              >
                Sem providência
              </Button>
              <Button
                type="button"
                disabled={saving || !deadline}
                onClick={async () => {
                  setSaving(true);
                  try {
                    await onReview({ approved: true, deadline_date: deadline });
                  } finally {
                    setSaving(false);
                  }
                }}
              >
                Confirmar prazo e criar tarefa
              </Button>
            </div>
          </>
        )
      ) : (
        <p className="text-sm text-muted">
          A IA não identificou prazo nesta intimação — nenhuma data foi sugerida.
        </p>
      )}
    </section>
  );
}

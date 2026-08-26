import { AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AgentGenerationData } from "@/features/legal-agents/api";

export interface GeneratedBriefPreviewProps {
  generation: AgentGenerationData;
  isSaving?: boolean;
  onOpenInEditor: () => void;
}

/** A minuta gerada (spec 087, regras 4 e 6).
 *
 * O aviso de MINUTA é fixo e não some: a peça saiu de um modelo de linguagem e precisa
 * de revisão de advogado antes de virar documento do processo. E quando o guarda-corpo
 * removeu alguma citação inventada, isso aparece — silenciar seria o pior dos mundos. */
export function GeneratedBriefPreview({
  generation,
  isSaving = false,
  onOpenInEditor,
}: GeneratedBriefPreviewProps): JSX.Element {
  return (
    <section data-testid="generated-brief" className="space-y-3">
      <p
        data-testid="draft-warning"
        role="alert"
        className="rounded border border-warning bg-warning/10 px-3 py-2 text-sm text-primary"
      >
        <strong>Minuta gerada por IA.</strong> Revise antes de usar: nada aqui foi conferido por um
        advogado, e o texto não é documento do processo até você salvar.
      </p>

      {generation.warnings.length > 0 && (
        <div
          data-testid="citation-warnings"
          className="space-y-1 rounded border border-danger bg-danger/10 px-3 py-2 text-sm"
        >
          <p className="flex items-center gap-2 font-medium text-danger">
            <AlertTriangle aria-hidden className="size-4" />
            Citações removidas por não constarem no processo
          </p>
          <ul className="list-disc pl-5 text-muted">
            {generation.warnings.map((warning, index) => (
              <li key={`${warning.text}-${index}`}>{warning.text}</li>
            ))}
          </ul>
        </div>
      )}

      <article
        data-testid="brief-content"
        className="prose max-w-none rounded border border-default bg-surface p-4 text-sm"
        // O HTML vem do próprio backend (mesma origem do editor da 065), já passado
        // pelo guarda-corpo de citações.
        dangerouslySetInnerHTML={{ __html: generation.content.html }}
      />

      <div className="flex items-center justify-between text-xs text-muted">
        <span>
          {generation.model}
          {generation.tokens_used ? ` · ${generation.tokens_used} tokens` : ""}
        </span>
        <Button type="button" disabled={isSaving} onClick={onOpenInEditor}>
          {generation.saved_template_id ? "Abrir no editor" : "Salvar e abrir no editor"}
        </Button>
      </div>
    </section>
  );
}

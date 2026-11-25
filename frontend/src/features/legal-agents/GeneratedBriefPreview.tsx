import { AlertTriangle } from "lucide-react";

import { SandboxedHtml } from "@/components/domain/SandboxedHtml";
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

      {/* Spec 138, regra 1: o HTML é escrito por um modelo de linguagem e gravado cru
          pelo backend — `strip_unsupported_citations` troca números de súmula, não
          sanitiza nada. Fora do sandbox, um `<img onerror>` numa minuta rodaria na nossa
          origem, onde mora o refresh token de 30 dias. */}
      <SandboxedHtml
        data-testid="brief-content"
        html={generation.content.html}
        title="Minuta gerada"
        className="w-full rounded border border-default bg-surface"
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

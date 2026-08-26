import { Loader2 } from "lucide-react";

export interface GenerationProgressProps {
  /** Rótulos em português do que o agente consultou ("abrindo o processo"). */
  toolLabels: string[];
  isGenerating: boolean;
}

/** O que o agente está fazendo enquanto a minuta não fica pronta (spec 087, regra 8).
 *
 * Gerar uma peça leva dezenas de segundos; sem isso a tela parece travada, e a pessoa
 * clica de novo. */
export function GenerationProgress({
  toolLabels,
  isGenerating,
}: GenerationProgressProps): JSX.Element | null {
  if (!isGenerating && toolLabels.length === 0) return null;
  return (
    <div data-testid="generation-progress" role="status" className="space-y-1 text-sm">
      <p className="flex items-center gap-2 text-primary">
        {isGenerating && <Loader2 aria-hidden className="size-4 animate-spin" />}
        {isGenerating ? "Escrevendo a minuta…" : "Minuta pronta."}
      </p>
      <ol className="space-y-0.5 text-xs text-muted">
        {toolLabels.map((label, index) => (
          <li key={`${label}-${index}`}>· {label}</li>
        ))}
      </ol>
    </div>
  );
}

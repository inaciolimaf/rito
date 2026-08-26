import * as React from "react";

export interface AiSuggestionOverlayProps {
  /** Texto sugerido, em construção — chega em pedaços pelo streaming. */
  suggestion: string;
  isStreaming: boolean;
  onAccept: () => void;
  onDiscard: () => void;
}

/** A sugestão da IA em cinza, antes de existir no documento (spec 088, regra 2).
 *
 * Tab aceita, Esc descarta — nada é inserido sem gesto. O atalho é global enquanto a
 * sugestão está na tela: quem está escrevendo não vai tirar a mão do teclado para
 * clicar num botão. */
export function AiSuggestionOverlay({
  suggestion,
  isStreaming,
  onAccept,
  onDiscard,
}: AiSuggestionOverlayProps): JSX.Element | null {
  React.useEffect(() => {
    function handle(event: KeyboardEvent): void {
      if (event.key === "Tab") {
        event.preventDefault();
        onAccept();
      }
      if (event.key === "Escape") {
        event.preventDefault();
        onDiscard();
      }
    }
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [onAccept, onDiscard]);

  if (!suggestion && !isStreaming) return null;
  return (
    <div
      data-testid="ai-suggestion"
      aria-live="polite"
      className="rounded border border-dashed border-accent bg-accent/5 p-3 text-sm"
    >
      <p className="whitespace-pre-wrap text-muted">
        {suggestion}
        {isStreaming && <span className="ml-0.5 animate-pulse">▍</span>}
      </p>
      <p className="mt-2 text-xs text-muted">
        <kbd className="rounded border border-default px-1">Tab</kbd> aceita ·{" "}
        <kbd className="rounded border border-default px-1">Esc</kbd> descarta
      </p>
    </div>
  );
}

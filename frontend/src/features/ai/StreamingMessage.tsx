export interface StreamingMessageProps {
  /** Pedaços já recebidos, na ordem — o componente só concatena. */
  chunks: string[];
  isStreaming: boolean;
}

/** A resposta em construção (spec 085, regra 2).
 *
 * O componente não sabe de onde vêm os pedaços: no SSE de hoje chega a resposta inteira
 * de uma vez; quando o streaming por token da 081 for ligado no nó do grafo, chegam
 * vários — e nada muda aqui. */
export function StreamingMessage({ chunks, isStreaming }: StreamingMessageProps): JSX.Element {
  const text = chunks.join("");
  return (
    <div
      data-testid="streaming-message"
      aria-live="polite"
      className="max-w-[85%] rounded-lg bg-surface-muted px-3 py-2 text-sm text-primary"
    >
      <p className="whitespace-pre-wrap">
        {text}
        {isStreaming && (
          <span data-testid="streaming-caret" className="ml-0.5 animate-pulse">
            ▍
          </span>
        )}
      </p>
    </div>
  );
}

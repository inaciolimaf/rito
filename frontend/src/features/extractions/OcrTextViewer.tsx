import * as React from "react";

export interface OcrTextViewerProps {
  text: string | null;
  usedOcr: boolean;
}

/** O texto cru lido do documento (spec 091, regra 10).
 *
 * Fica recolhido porque ninguém quer ler OCR — até o momento em que um campo parece
 * errado, e aí é a única forma de descobrir se o problema foi a foto ou o modelo. */
export function OcrTextViewer({ text, usedOcr }: OcrTextViewerProps): JSX.Element | null {
  const [aberto, setAberto] = React.useState(false);
  if (!text) return null;
  return (
    <div className="rounded border border-default">
      <button
        type="button"
        className="w-full px-3 py-2 text-left text-xs text-muted"
        onClick={() => setAberto((atual) => !atual)}
        aria-expanded={aberto}
      >
        {aberto ? "Ocultar" : "Ver"} o texto lido do documento{usedOcr ? " (OCR)" : ""}
      </button>
      {aberto && (
        <pre className="max-h-60 overflow-auto whitespace-pre-wrap px-3 pb-3 text-xs text-muted">
          {text}
        </pre>
      )}
    </div>
  );
}

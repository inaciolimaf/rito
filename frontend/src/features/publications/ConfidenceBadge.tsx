/** Confiança da IA no prazo que ela leu (spec 086, regra 4).
 *
 * O corte em 0,8 não é decoração: abaixo dele o campo de prazo não vem preenchido, e o
 * badge muda de tom para que a diferença seja visível antes de alguém clicar. */
export interface ConfidenceBadgeProps {
  confidence: number | null;
}

export const PREFILL_THRESHOLD = 0.8;

export function ConfidenceBadge({ confidence }: ConfidenceBadgeProps): JSX.Element | null {
  if (confidence === null) return null;
  const alta = confidence >= PREFILL_THRESHOLD;
  return (
    <span
      data-testid="confidence-badge"
      data-level={alta ? "high" : "low"}
      title={
        alta
          ? "A IA está confiante na leitura do prazo — confira mesmo assim."
          : "Confiança baixa: o prazo NÃO foi preenchido. Leia o inteiro teor antes de confirmar."
      }
      className={
        alta
          ? "inline-flex items-center rounded-full bg-success/15 px-2 py-0.5 text-xs font-medium text-success"
          : "inline-flex items-center rounded-full bg-warning/20 px-2 py-0.5 text-xs font-medium text-warning"
      }
    >
      confiança {Math.round(confidence * 100)}%
    </span>
  );
}

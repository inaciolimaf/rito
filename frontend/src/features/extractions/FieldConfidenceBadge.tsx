export interface FieldConfidenceBadgeProps {
  confidence: number;
  isValid: boolean;
}

/** Quanto o sistema confia naquele valor (spec 091, regras 3 e 4).
 *
 * São duas informações diferentes e a tela não pode fundi-las: confiança é sobre a
 * LEITURA ("o OCR viu isso mesmo?"), validade é sobre o VALOR ("esse CPF existe?"). Um
 * CPF lido com nitidez perfeita e dígito verificador errado é alta confiança e inválido
 * — e é exatamente o caso em que a pessoa precisa olhar. */
export function FieldConfidenceBadge({
  confidence,
  isValid,
}: FieldConfidenceBadgeProps): JSX.Element {
  const pct = Math.round(confidence * 100);
  const baixa = confidence < 0.7;
  return (
    <span className="flex items-center gap-1">
      <span
        className={`rounded px-1.5 py-0.5 text-[11px] ${
          baixa ? "bg-warning/20 text-warning" : "bg-success/20 text-success"
        }`}
        title={baixa ? "Leitura incerta — confira no documento" : "Leitura confiável"}
      >
        {pct}%
      </span>
      {!isValid && (
        <span
          className="rounded bg-danger/20 px-1.5 py-0.5 text-[11px] text-danger"
          title="O dígito verificador não fecha — pode ser erro de leitura"
        >
          inválido
        </span>
      )}
    </span>
  );
}

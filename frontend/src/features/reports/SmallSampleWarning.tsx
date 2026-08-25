export interface SmallSampleWarningProps {
  /** Quantos concluídos/processos o indicador exige para significar alguma coisa
   * (10 nas safras e na taxa de sucesso, 5 na rentabilidade por tipo). */
  minimum: number;
  /** O que está sendo contado, para o texto ficar honesto em cada aba. */
  unit?: string;
  /** `icon` dentro de célula de tabela; `text` embaixo de um card. */
  variant?: "icon" | "text";
}

/** Aviso de amostra pequena (specs 075 regra 5, 076 regra 9) — estava escrito três
 * vezes com três textos ligeiramente diferentes (refatoração 080, regra dos 3 usos). */
export function SmallSampleWarning({
  minimum,
  unit = "processos concluídos",
  variant = "icon",
}: SmallSampleWarningProps): JSX.Element {
  const message = `Amostra pequena: menos de ${minimum} ${unit}`;
  if (variant === "icon") {
    return (
      <span className="text-xs text-warning" title={message} data-testid="small-sample-warning">
        ⚠
      </span>
    );
  }
  return (
    <p className="mt-1 text-xs text-warning" role="note" data-testid="small-sample-warning">
      {message} — o indicador pode não significar nada.
    </p>
  );
}

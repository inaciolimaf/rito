export interface AllocationExplainerProps {
  /** A fórmula do rateio — vem pronta da API (`allocation_note`), para a redação
   * morar num lugar só (mesmo padrão do `rate_note` da 075). */
  note: string;
}

/** Tooltip que explica a fórmula do rateio de custo (spec 077, regra 11): o rateio é
 * uma aproximação — custo direto + pontos das tarefas × custo por ponto do mês — e o
 * tooltip existe para ninguém tratar o número como contabilidade. */
export function AllocationExplainer({ note }: AllocationExplainerProps): JSX.Element {
  return (
    <span
      className="cursor-help text-xs text-muted"
      title={note}
      data-testid="allocation-explainer"
      aria-label="Como o custo alocado é calculado"
    >
      ⓘ
    </span>
  );
}

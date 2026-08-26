import { Loader2 } from "lucide-react";

export interface ToolCallIndicatorProps {
  /** Rótulos em português vindos do backend ("consultando processos"). */
  labels: string[];
  isRunning?: boolean;
}

/** O que o agente está fazendo enquanto o usuário espera (spec 085, regra 3).
 *
 * O texto vem pronto do backend de propósito: nome de ferramenta é jargão, e traduzir
 * no frontend criaria uma segunda tabela de rótulos para divergir da primeira. */
export function ToolCallIndicator({
  labels,
  isRunning = true,
}: ToolCallIndicatorProps): JSX.Element | null {
  if (labels.length === 0) return null;
  return (
    <p
      data-testid="tool-call-indicator"
      className="flex items-center gap-2 text-xs text-muted"
      role="status"
    >
      {isRunning && <Loader2 aria-hidden className="size-3 animate-spin" />}
      {labels.join(" · ")}
      {isRunning ? "…" : ""}
    </p>
  );
}

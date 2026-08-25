import { AlertTriangle, CheckCircle2, CircleDot, PauseCircle } from "lucide-react";

import { EmptyState } from "@/components/domain/EmptyState";
import type { StepData } from "@/features/ai/threads";

const ICON_BY_KIND: Record<string, typeof CircleDot> = {
  interrupt: PauseCircle,
  error: AlertTriangle,
  end: CheckCircle2,
};

const LABEL_BY_KIND: Record<string, string> = {
  node: "Passo",
  llm: "Consultou o modelo",
  tool: "Usou uma ferramenta",
  interrupt: "Pediu confirmação",
  error: "Falhou",
  end: "Concluiu",
};

function describeOutput(step: StepData): string | null {
  if (step.error) return step.error;
  if (!step.output) return null;
  if (step.output.truncated === true) {
    const size = Number(step.output.size_bytes ?? 0);
    return `Resultado grande demais para guardar (${Math.round(size / 1024)} KB) — só a referência ficou.`;
  }
  return Object.keys(step.output).join(", ") || null;
}

export interface AgentStepsTimelineProps {
  steps: StepData[];
  isLoading?: boolean;
}

/** O que o agente fez, na ordem (spec 082, regra 7). É a tela que responde "por que o
 * sistema fez isso?" — por isso mostra o passo mesmo quando ele falhou. */
export function AgentStepsTimeline({
  steps,
  isLoading = false,
}: AgentStepsTimelineProps): JSX.Element {
  if (isLoading) {
    return <div className="h-24 animate-pulse rounded bg-surface-muted" />;
  }
  if (steps.length === 0) {
    return (
      <EmptyState
        title="Nenhum passo ainda"
        description="Os passos aparecem aqui conforme o agente trabalha."
      />
    );
  }
  return (
    <ol data-testid="agent-steps" className="space-y-2">
      {steps.map((step) => {
        const Icon = ICON_BY_KIND[step.kind] ?? CircleDot;
        const detail = describeOutput(step);
        return (
          <li
            key={step.id}
            className="flex gap-3 rounded border border-default bg-surface p-3 text-sm"
          >
            <Icon
              aria-hidden
              className={step.error ? "size-4 text-danger" : "size-4 text-accent"}
            />
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 text-primary">
                <span className="font-medium">
                  {step.step}. {LABEL_BY_KIND[step.kind] ?? step.kind}
                </span>
                <span className="text-xs text-muted">{step.node}</span>
                {step.duration_ms !== null && (
                  <span className="text-xs text-muted">{step.duration_ms} ms</span>
                )}
              </p>
              {detail && (
                <p className={step.error ? "truncate text-danger" : "truncate text-muted"}>
                  {detail}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

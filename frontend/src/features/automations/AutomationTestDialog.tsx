import { useMutation } from "@tanstack/react-query";
import * as React from "react";

import { testAutomation, type TestResultData } from "@/features/automations/api";
import { ACTION_LABELS, STATUS_LABELS } from "@/features/automations/labels";

export interface AutomationTestDialogProps {
  automationId: string;
  /** O retrato do sujeito que a simulação deve considerar (ex.: um processo real). */
  defaultPayload?: Record<string, unknown>;
}

/** Simulação (spec 092, regra 10): mostra o que aconteceria e não grava nada.
 *
 * O aviso de que nada foi gravado vem do servidor (`persisted`), não de um texto fixo:
 * é o tipo de garantia que não pode depender de alguém lembrar de atualizar a legenda. */
export function AutomationTestDialog({
  automationId,
  defaultPayload = {},
}: AutomationTestDialogProps): JSX.Element {
  const [resultado, setResultado] = React.useState<TestResultData | null>(null);
  const simular = useMutation({
    mutationFn: () => testAutomation(automationId, defaultPayload),
    onSuccess: setResultado,
  });

  return (
    <div className="space-y-2">
      <button
        type="button"
        className="rounded border border-default px-3 py-1 text-sm"
        onClick={() => simular.mutate()}
        disabled={simular.isPending}
      >
        Testar automação
      </button>

      {resultado && (
        <div className="space-y-2" aria-label="Resultado da simulação">
          {!resultado.persisted && (
            <p className="text-xs text-muted">
              Simulação: nada foi gravado. É só o que aconteceria.
            </p>
          )}
          <ol className="space-y-1">
            {resultado.steps.map((passo) => (
              <li key={passo.position} className="rounded border border-default p-2 text-sm">
                <strong>{ACTION_LABELS[passo.action_kind]}</strong>
                {" — "}
                {STATUS_LABELS[passo.status] ?? passo.status}
                {passo.scheduled_for && (
                  <span className="text-muted">
                    {" "}
                    em {new Date(`${passo.scheduled_for}T12:00:00`).toLocaleDateString("pt-BR")}
                  </span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

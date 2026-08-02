import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { Label } from "@/components/ui/label";
import { listStages, listSteps } from "@/features/stages/api";

const SELECT_CLASS =
  "h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export interface StageStepSelectProps {
  value: string;
  onChange: (stageId: string) => void;
  /** Fase da etapa atual (spec 022 §6: "etapa filtra por fase e vice-versa") — ao editar
   * um processo já existe uma etapa selecionada, e é ela quem determina a fase inicial do
   * seletor (o formulário nunca guarda `step_id`, só `stage_id`). */
  initialStepId?: number | null;
}

/** Fase filtra as etapas disponíveis; trocar de fase limpa a etapa escolhida (mesmo padrão
 * de `StateCitySelect`, spec 018: trocar o valor "pai" limpa o "filho"). */
export function StageStepSelect({
  value,
  onChange,
  initialStepId,
}: StageStepSelectProps): JSX.Element {
  const [stepId, setStepId] = React.useState<number | "">(initialStepId ?? "");

  React.useEffect(() => {
    if (initialStepId != null) setStepId(initialStepId);
  }, [initialStepId]);

  const { data: steps = [] } = useQuery({ queryKey: ["steps"], queryFn: listSteps });

  const { data: stagesPage } = useQuery({
    queryKey: ["stages", "for-lawsuit-form", stepId],
    queryFn: () => listStages({ step_id: stepId === "" ? undefined : stepId, status: "active" }),
    enabled: stepId !== "",
  });
  const stages = stagesPage?.items ?? [];

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="space-y-1">
        <Label htmlFor="lawsuit-step">Fase</Label>
        <select
          id="lawsuit-step"
          className={SELECT_CLASS}
          value={stepId}
          onChange={(event) => {
            const next = event.target.value ? Number(event.target.value) : "";
            setStepId(next);
            onChange("");
          }}
        >
          <option value="">Selecione</option>
          {steps.map((step) => (
            <option key={step.id} value={step.id}>
              {step.name}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        <Label htmlFor="lawsuit-stage">Etapa</Label>
        {stepId === "" ? (
          <p className="text-sm text-muted">Selecione uma fase primeiro.</p>
        ) : (
          <select
            id="lawsuit-stage"
            className={SELECT_CLASS}
            value={value}
            onChange={(event) => onChange(event.target.value)}
          >
            <option value="">Selecione</option>
            {stages.map((stage) => (
              <option key={stage.id} value={stage.id}>
                {stage.name}
              </option>
            ))}
          </select>
        )}
      </div>
    </div>
  );
}

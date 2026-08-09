import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listUsers } from "@/features/users/api";
import type { WorkflowDetail, WorkflowPayload } from "@/features/workflows/api";
import { WorkflowStepRow, type WorkflowStepValue } from "@/features/workflows/WorkflowStepRow";

export interface WorkflowEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** null = criação; com valor = edição (passos vêm do detalhe). */
  initial: WorkflowDetail | null;
  onSubmit: (payload: WorkflowPayload) => Promise<void>;
}

const EMPTY_STEP: WorkflowStepValue = { task_type_id: "", user_id: null, days_offset: "" };

/** Editor da sequência (spec 038 §6): nome + lista ordenável de etapas. A posição é
 * a ordem do array — o PUT reconcilia o conjunto inteiro (regra 11). */
export function WorkflowEditor({
  open,
  onOpenChange,
  initial,
  onSubmit,
}: WorkflowEditorProps): JSX.Element {
  const [name, setName] = React.useState("");
  const [steps, setSteps] = React.useState<WorkflowStepValue[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    setName(initial?.name ?? "");
    setSteps(
      initial?.steps.map((step) => ({
        task_type_id: step.task_type_id,
        user_id: step.user_id,
        days_offset: step.days_offset != null ? String(step.days_offset) : "",
      })) ?? [],
    );
    setError(null);
  }, [open, initial]);

  const { data: usersPage } = useQuery({
    queryKey: ["users", "for-workflow-editor"],
    queryFn: () => listUsers({ limit: 100 }),
    enabled: open,
  });
  const userOptions = (usersPage?.items ?? []).map((user) => ({
    value: user.id,
    label: user.name,
  }));

  function changeStep(index: number, next: WorkflowStepValue): void {
    setSteps((current) => current.map((step, i) => (i === index ? next : step)));
  }

  function moveStep(index: number, direction: -1 | 1): void {
    setSteps((current) => {
      const next = [...current];
      const moved = next.splice(index, 1)[0];
      if (moved === undefined) return current;
      next.splice(index + direction, 0, moved);
      return next;
    });
  }

  function removeStep(index: number): void {
    setSteps((current) => current.filter((_step, i) => i !== index));
  }

  async function handleSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!name.trim()) {
      setError("Informe o nome do workflow.");
      return;
    }
    if (steps.some((step) => !step.task_type_id)) {
      setError("Toda etapa precisa de um tipo de tarefa (regra 1).");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        name: name.trim(),
        is_active: initial?.is_active ?? true,
        steps: steps.map((step) => ({
          task_type_id: step.task_type_id,
          user_id: step.user_id,
          days_offset: step.days_offset === "" ? null : Number(step.days_offset),
        })),
      });
      onOpenChange(false);
    } catch {
      setError("Não foi possível salvar. Verifique o nome (único por escritório).");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogTitle>{initial ? "Editar workflow" : "Novo workflow"}</DialogTitle>
        <DialogDescription>
          Sequência de tarefas gerada ao mover o processo de etapa. O prazo conta dias úteis a
          partir do disparo (feriados nacionais pulados).
        </DialogDescription>
        <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-col gap-3">
          <div className="space-y-1">
            <Label htmlFor="workflow-name">Nome</Label>
            <Input
              id="workflow-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Ex.: Contencioso — entrada de ação"
            />
          </div>

          <div className="flex flex-col gap-2" data-testid="workflow-steps">
            {steps.length === 0 && (
              <p className="text-sm text-muted">Nenhuma etapa ainda — adicione a primeira.</p>
            )}
            {steps.map((step, index) => (
              <WorkflowStepRow
                key={index}
                step={step}
                index={index}
                total={steps.length}
                userOptions={userOptions}
                onChange={changeStep}
                onMove={moveStep}
                onRemove={removeStep}
              />
            ))}
          </div>

          <div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setSteps((current) => [...current, { ...EMPTY_STEP }])}
            >
              Adicionar etapa
            </Button>
          </div>

          {error && <p className="text-sm text-danger">{error}</p>}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" disabled={submitting}>
              Salvar
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

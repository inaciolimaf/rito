import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { listLawsuits } from "@/features/lawsuits/api";
import { applyWorkflow, previewWorkflow, type WorkflowPreview } from "@/features/workflows/api";

export interface WorkflowPreviewDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowId: string | null;
  workflowName?: string;
  /** Quando já vem da troca de etapa (regra 7), o processo é conhecido; na aplicação
   * manual (§2) o usuário escolhe aqui. */
  lawsuit?: EntityOption | null;
}

async function searchLawsuits(query: string): Promise<EntityOption[]> {
  const page = await listLawsuits({ q: query, limit: 20 });
  return page.items.map((item) => {
    const firstParty = item.parties[0]?.name;
    const number = item.process_number ?? item.folder ?? "s/nº";
    return { id: item.id, label: `${firstParty ?? "Processo"} — ${number}` };
  });
}

function formatDate(iso: string | null): string {
  if (!iso) return "Sem prazo";
  const [year = 0, month = 1, day = 1] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("pt-BR");
}

/** Preview antes de aplicar (spec 038, regras 6–8): lista EXATAMENTE o que será
 * criado, avisa etapas puladas e exige confirmação extra na reaplicação. */
export function WorkflowPreviewDialog({
  open,
  onOpenChange,
  workflowId,
  workflowName,
  lawsuit = null,
}: WorkflowPreviewDialogProps): JSX.Element {
  const queryClient = useQueryClient();
  const [selected, setSelected] = React.useState<EntityOption | null>(null);
  const [appliedMessage, setAppliedMessage] = React.useState<string | null>(null);
  const [applying, setApplying] = React.useState(false);
  const [applyError, setApplyError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (open) {
      setSelected(lawsuit);
      setAppliedMessage(null);
      setApplyError(null);
    } else {
      setSelected(null);
    }
  }, [open, lawsuit]);

  const { data: preview, isLoading } = useQuery<WorkflowPreview>({
    queryKey: ["workflow-preview", workflowId, selected?.id],
    queryFn: () => previewWorkflow(workflowId!, selected!.id),
    enabled: open && workflowId !== null && selected !== null,
  });

  async function handleApply(confirmDuplicate: boolean): Promise<void> {
    if (!workflowId || !selected) return;
    setApplying(true);
    setApplyError(null);
    try {
      const result = await applyWorkflow(workflowId, selected.id, confirmDuplicate);
      setAppliedMessage(
        `${result.created} tarefa(s) criada(s)${result.skipped.length > 0 ? `, ${result.skipped.length} etapa(s) pulada(s)` : ""}.`,
      );
      await queryClient.invalidateQueries({ queryKey: ["lawsuit-posts"] });
      await queryClient.invalidateQueries({ queryKey: ["posts"] });
    } catch {
      setApplyError("Não foi possível aplicar o workflow — nenhuma tarefa foi criada.");
    } finally {
      setApplying(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Aplicar workflow{workflowName ? ` — ${workflowName}` : ""}</DialogTitle>
        <DialogDescription>
          Revise as tarefas que serão criadas. Nada é gravado antes da confirmação.
        </DialogDescription>

        {appliedMessage ? (
          <p data-testid="workflow-applied-message" className="text-sm text-success">
            {appliedMessage}
          </p>
        ) : (
          <>
            {!selected && (
              <div className="space-y-1">
                <span className="text-sm font-medium">Processo</span>
                <EntityPicker
                  placeholder="Buscar por cliente ou número…"
                  value={[]}
                  onChange={(next) => setSelected(next[0] ?? null)}
                  onSearch={searchLawsuits}
                />
              </div>
            )}
            {selected && (
              <p className="text-sm text-muted">
                Processo: <span className="text-primary">{selected.label}</span>
              </p>
            )}

            {isLoading && selected && <p className="text-sm text-muted">Carregando…</p>}

            {preview && (
              <div data-testid="workflow-preview" className="flex flex-col gap-2">
                <ul className="flex flex-col divide-y divide-default rounded border border-default">
                  {preview.tasks.map((task, index) => (
                    <li key={index} className="flex items-center gap-3 px-3 py-2 text-sm">
                      <span className="w-5 text-muted">{index + 1}.</span>
                      <span className="flex-1">{task.task_type_name}</span>
                      <span className="text-muted">{task.user_name}</span>
                      <span className="w-24 text-right">{formatDate(task.date)}</span>
                    </li>
                  ))}
                  {preview.tasks.length === 0 && (
                    <li className="px-3 py-2 text-sm text-muted">
                      Nenhuma tarefa a criar — todas as etapas foram puladas.
                    </li>
                  )}
                </ul>
                {preview.skipped.map((item, index) => (
                  <p key={index} className="text-sm text-warning">
                    ⚠ {item.task_type_name}: {item.reason}
                  </p>
                ))}
                {preview.already_applied && (
                  <p data-testid="workflow-already-applied" className="text-sm text-warning">
                    ⚠ Este workflow já gerou tarefas neste processo (regra 8). Aplicar de novo cria
                    tarefas duplicadas.
                  </p>
                )}
              </div>
            )}

            {applyError && <p className="text-sm text-danger">{applyError}</p>}

            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancelar
              </Button>
              <Button
                type="button"
                disabled={!preview || preview.tasks.length === 0 || applying}
                onClick={() => void handleApply(preview?.already_applied ?? false)}
              >
                {preview?.already_applied ? "Aplicar mesmo assim" : "Aplicar workflow"}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

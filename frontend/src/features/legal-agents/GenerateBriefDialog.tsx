import { useMutation, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  generateBrief,
  listLegalAgents,
  saveGenerationAsTemplate,
  type AgentGenerationData,
  type LegalAgentData,
} from "@/features/legal-agents/api";
import { AgentPickerDialog } from "@/features/legal-agents/AgentPickerDialog";
import { GeneratedBriefPreview } from "@/features/legal-agents/GeneratedBriefPreview";
import { GenerationProgress } from "@/features/legal-agents/GenerationProgress";

export interface GenerateBriefDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  lawsuitId: string;
  /** Chamado depois de salvar: leva o usuário ao editor com o documento criado. */
  onOpenTemplate: (templateId: string) => void;
}

/** Gerar uma minuta para um processo (spec 087 §6): escolher o agente, dar instruções,
 * acompanhar o que ele consultou e decidir o que fazer com o resultado. */
export function GenerateBriefDialog({
  open,
  onOpenChange,
  lawsuitId,
  onOpenTemplate,
}: GenerateBriefDialogProps): JSX.Element {
  const [agent, setAgent] = React.useState<LegalAgentData | null>(null);
  const [pickerOpen, setPickerOpen] = React.useState(false);
  const [instructions, setInstructions] = React.useState("");
  const [generation, setGeneration] = React.useState<AgentGenerationData | null>(null);

  const { data: agents } = useQuery({
    queryKey: ["legal-agents"],
    queryFn: listLegalAgents,
    enabled: open,
  });

  const generate = useMutation({
    mutationFn: () =>
      generateBrief(agent!.id, {
        lawsuit_id: lawsuitId,
        instructions: instructions.trim() || undefined,
      }),
    onSuccess: setGeneration,
  });

  const save = useMutation({
    mutationFn: () => saveGenerationAsTemplate(generation!.id),
    onSuccess: (result) => onOpenTemplate(result.template_id),
  });

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-2xl">
          <DialogTitle>Gerar minuta com IA</DialogTitle>
          <DialogDescription>
            O agente consulta o processo no sistema — não há base externa nem jurisprudência que não
            esteja aqui dentro.
          </DialogDescription>

          <div className="mt-4 space-y-3">
            <div className="space-y-1">
              <Label>Agente</Label>
              <Button
                type="button"
                variant="outline"
                className="w-full justify-start"
                onClick={() => setPickerOpen(true)}
              >
                {agent ? `${agent.practice_area} — ${agent.name}` : "Escolher agente…"}
              </Button>
            </div>

            <div className="space-y-1">
              <Label htmlFor="brief-instructions">Instruções (opcional)</Label>
              <textarea
                id="brief-instructions"
                rows={3}
                className="w-full rounded border border-default bg-surface p-2 text-sm"
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                placeholder="Ex.: foque no adicional de insalubridade e seja breve."
              />
            </div>

            <GenerationProgress
              toolLabels={generation?.tool_labels ?? []}
              isGenerating={generate.isPending}
            />

            {generation ? (
              <GeneratedBriefPreview
                generation={generation}
                isSaving={save.isPending}
                onOpenInEditor={() => save.mutate()}
              />
            ) : (
              <div className="flex justify-end">
                <Button
                  type="button"
                  disabled={!agent || generate.isPending}
                  onClick={() => generate.mutate()}
                >
                  Gerar minuta
                </Button>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <AgentPickerDialog
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        agents={agents?.items ?? []}
        onPick={(picked) => {
          setAgent(picked);
          setPickerOpen(false);
        }}
      />
    </>
  );
}

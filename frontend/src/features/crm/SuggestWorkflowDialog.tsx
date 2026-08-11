import type { EntityOption } from "@/components/domain/types";
import { applyLawsuitWorkflow, suppressLawsuitWorkflow } from "@/features/crm/api";
import { WorkflowPreviewDialog } from "@/features/workflows/WorkflowPreviewDialog";

export interface SuggestWorkflowDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workflowId: string;
  workflowName: string;
  lawsuit: EntityOption;
  stageId: string;
  onSuppressed?: () => void;
}

/** Diálogo de sugestão ao mover etapa (spec 053, regras 1/2/6) — mesmo preview +
 * aplicar de `WorkflowPreviewDialog` (spec 038), mas aplicar aqui grava em
 * `workflow_applications` (permite desfazer) e ganha o botão "não sugerir novamente". */
export function SuggestWorkflowDialog({
  open,
  onOpenChange,
  workflowId,
  workflowName,
  lawsuit,
  stageId,
  onSuppressed,
}: SuggestWorkflowDialogProps): JSX.Element {
  return (
    <WorkflowPreviewDialog
      open={open}
      onOpenChange={onOpenChange}
      workflowId={workflowId}
      workflowName={workflowName}
      lawsuit={lawsuit}
      applyFn={(workflow, targetLawsuit, confirmDuplicate) =>
        applyLawsuitWorkflow(workflow, targetLawsuit, confirmDuplicate, stageId)
      }
      onSuppress={() => {
        void suppressLawsuitWorkflow(lawsuit.id, stageId).then(() => onSuppressed?.());
      }}
    />
  );
}

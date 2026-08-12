import type { ApplyResult } from "@/features/workflows/api";
import { apiRequest } from "@/lib/api";

export interface BoardCard {
  id: string;
  process_number: string | null;
  folder: string | null;
  lawsuit_type_name: string;
  stage_id: string;
  stage_name: string;
  case_value: number | null;
  responsible_id: string;
  responsible_name: string;
  stage_entered_at: string;
  parties: { name: string; pole: string | null }[];
  parties_total: number;
  is_stagnant: boolean;
  stagnant_since: string | null;
  stagnant_days: number | null;
}

export interface BoardColumn {
  step_id: number;
  step_name: string;
  total: number;
  items: BoardCard[];
}

export interface Board {
  columns: BoardColumn[];
  total: number;
  suggest_refine_filters: boolean;
}

export interface BoardColumnPage {
  items: BoardCard[];
  next_cursor: string | null;
  total: number;
}

export interface BoardFilters {
  view?: string;
  q?: string;
  action_group_id?: string;
  lawsuit_type_id?: string;
  user_id?: string;
  archived?: boolean;
  display_stagnant?: "all" | "stagnant" | "active";
}

export interface CrmStatsByStep {
  step_id: number;
  step_name: string;
  total: number;
  stagnant_count: number;
}

export interface CrmStats {
  total_lawsuits: number;
  received_this_month: number;
  // null quando financial_access=NONE (refatoração 060, Alvo 3).
  total_value: number | null;
  stagnant_count: number;
  stagnant_value: number | null;
  by_step: CrmStatsByStep[];
}

export interface SuggestedWorkflow {
  id: string;
  name: string;
}

function toQuery(params: object): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export async function getBoard(filters: BoardFilters = {}): Promise<Board> {
  return apiRequest<Board>(`/api/v1/crm/board${toQuery(filters)}`);
}

export async function getBoardColumn(
  stepId: number,
  params: BoardFilters & { cursor?: string; limit?: number } = {},
): Promise<BoardColumnPage> {
  return apiRequest<BoardColumnPage>(`/api/v1/crm/board/column/${stepId}${toQuery(params)}`);
}

export async function moveLawsuitStage(
  lawsuitId: string,
  stageId: string,
): Promise<{ suggested_workflow: SuggestedWorkflow | null }> {
  const result = await apiRequest<{ suggested_workflow: SuggestedWorkflow | null }>(
    `/api/v1/lawsuits/${lawsuitId}/move-stage`,
    { method: "POST", body: { stage_id: stageId } },
  );
  return { suggested_workflow: result.suggested_workflow };
}

export async function applyLawsuitWorkflow(
  workflowId: string,
  lawsuitId: string,
  confirmDuplicate: boolean,
  stageId: string | null = null,
): Promise<ApplyResult> {
  return apiRequest<ApplyResult>(`/api/v1/lawsuits/${lawsuitId}/apply-workflow`, {
    method: "POST",
    body: { workflow_id: workflowId, stage_id: stageId, confirm_duplicate: confirmDuplicate },
  });
}

export async function suppressLawsuitWorkflow(lawsuitId: string, stageId: string): Promise<void> {
  await apiRequest(`/api/v1/lawsuits/${lawsuitId}/suppress-workflow`, {
    method: "POST",
    body: { stage_id: stageId },
  });
}

export async function bulkMoveLawsuitStage(
  lawsuitIds: string[],
  stageId: string,
): Promise<{ moved: number }> {
  return apiRequest<{ moved: number }>("/api/v1/lawsuits/bulk/move-stage", {
    method: "POST",
    body: { lawsuit_ids: lawsuitIds, stage_id: stageId },
  });
}

export async function getCrmStats(filters: BoardFilters = {}): Promise<CrmStats> {
  return apiRequest<CrmStats>(`/api/v1/crm/stats${toQuery(filters)}`);
}

export async function recalculateStagnation(): Promise<{ recalculated_count: number }> {
  return apiRequest<{ recalculated_count: number }>("/api/v1/crm/recalculate-stagnation", {
    method: "POST",
  });
}

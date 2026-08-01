import { apiRequest } from "@/lib/api";
import type { ListResponse } from "@/components/domain/types";

export interface StepData {
  id: number;
  name: string;
  position: number;
}

export async function listSteps(): Promise<StepData[]> {
  return apiRequest<StepData[]>("/api/v1/steps");
}

export interface StageData {
  id: string;
  name: string;
  step_id: number;
  step_name: string;
  position: number;
  enable_stagnant_days: boolean;
  stagnant_days: number | null;
  suggested_workflow_id: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ListStagesParams {
  step_id?: number;
  status?: "active" | "inactive";
  q?: string;
}

export async function listStages(params: ListStagesParams): Promise<ListResponse<StageData>> {
  const query = new URLSearchParams();
  if (params.step_id !== undefined) query.set("step_id", String(params.step_id));
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);

  const queryString = query.toString();
  return apiRequest<ListResponse<StageData>>(
    `/api/v1/stages${queryString ? `?${queryString}` : ""}`,
  );
}

export interface StageFormPayload {
  name: string;
  step_id: number;
  enable_stagnant_days?: boolean;
  stagnant_days?: number | null;
  is_active?: boolean;
}

export async function createStage(values: StageFormPayload): Promise<StageData> {
  return apiRequest<StageData>("/api/v1/stages", { method: "POST", body: values });
}

export async function updateStage(id: string, values: StageFormPayload): Promise<StageData> {
  return apiRequest<StageData>(`/api/v1/stages/${id}`, { method: "PUT", body: values });
}

export async function deleteStage(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/stages/${id}`, { method: "DELETE" });
}

export async function reorderStages(stageIds: string[]): Promise<{ reordered_count: number }> {
  return apiRequest<{ reordered_count: number }>("/api/v1/stages/reorder", {
    method: "POST",
    body: { stage_ids: stageIds },
  });
}

export async function transferStages(
  fromId: string,
  toId: string,
): Promise<{ transferred_count: number }> {
  return apiRequest<{ transferred_count: number }>("/api/v1/stages/transfer", {
    method: "POST",
    body: { from_id: fromId, to_id: toId },
  });
}

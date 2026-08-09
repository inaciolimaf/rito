import { apiRequest } from "@/lib/api";

export interface WorkflowStepData {
  task_type_id: string;
  task_type_name: string;
  user_id: string | null;
  user_name: string | null;
  days_offset: number | null;
}

export interface WorkflowStepPayload {
  task_type_id: string;
  user_id?: string | null;
  days_offset?: number | null;
}

export interface WorkflowListItem {
  id: string;
  name: string;
  is_active: boolean;
  step_count: number;
}

export interface WorkflowDetail {
  id: string;
  name: string;
  is_active: boolean;
  steps: WorkflowStepData[];
}

export interface WorkflowPayload {
  name: string;
  is_active: boolean;
  steps: WorkflowStepPayload[];
}

export interface PreviewTask {
  task_type_name: string;
  user_id: string;
  user_name: string;
  date: string | null;
}

export interface SkippedStep {
  task_type_name: string;
  reason: string;
}

export interface WorkflowPreview {
  tasks: PreviewTask[];
  skipped: SkippedStep[];
  already_applied: boolean;
}

export interface ApplyResult {
  created: number;
  post_ids: string[];
  skipped: SkippedStep[];
}

export async function listWorkflows(params: {
  status?: string;
  q?: string;
}): Promise<WorkflowListItem[]> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  const suffix = query.size > 0 ? `?${query}` : "";
  const body = await apiRequest<{ items: WorkflowListItem[] }>(`/api/v1/workflows${suffix}`);
  return body.items;
}

export async function getWorkflow(id: string): Promise<WorkflowDetail> {
  return apiRequest<WorkflowDetail>(`/api/v1/workflows/${id}`);
}

export async function createWorkflow(payload: WorkflowPayload): Promise<WorkflowDetail> {
  return apiRequest<WorkflowDetail>("/api/v1/workflows", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateWorkflow(
  id: string,
  payload: WorkflowPayload,
): Promise<WorkflowDetail> {
  return apiRequest<WorkflowDetail>(`/api/v1/workflows/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteWorkflow(id: string): Promise<void> {
  return apiRequest<void>(`/api/v1/workflows/${id}`, { method: "DELETE" });
}

export async function previewWorkflow(id: string, lawsuitId: string): Promise<WorkflowPreview> {
  return apiRequest<WorkflowPreview>(`/api/v1/workflows/${id}/preview`, {
    method: "POST",
    body: JSON.stringify({ lawsuit_id: lawsuitId }),
  });
}

export async function applyWorkflow(
  id: string,
  lawsuitId: string,
  confirmDuplicate: boolean,
): Promise<ApplyResult> {
  return apiRequest<ApplyResult>(`/api/v1/workflows/${id}/apply`, {
    method: "POST",
    body: JSON.stringify({ lawsuit_id: lawsuitId, confirm_duplicate: confirmDuplicate }),
  });
}

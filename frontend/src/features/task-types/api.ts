import { apiRequest } from "@/lib/api";

export type TaskComplexity = "SIMPLES" | "MEDIA" | "MEDIA_ALTA" | "ALTA" | "ALTISSIMA";
export type TaskDuration = "MIN_8" | "MIN_15" | "MIN_30" | "HOUR_1" | "HOUR_2_PLUS";

export interface TaskTypeData {
  id: string;
  name: string;
  step_id: number | null;
  step_name: string | null;
  complexity: TaskComplexity | null;
  duration: TaskDuration | null;
  reward: number;
  show_in_schedule: boolean;
  is_system: boolean;
  is_active: boolean;
  last_assigned_at: string | null;
  created_at: string;
}

export interface TaskTypeListParams {
  step_id?: number;
  status?: "active" | "inactive";
  q?: string;
}

export interface TaskTypePayload {
  name: string;
  step_id: number | null;
  complexity: TaskComplexity | null;
  duration: TaskDuration | null;
  reward: number | null;
  show_in_schedule: boolean;
  is_active?: boolean;
}

export async function listTaskTypes(params: TaskTypeListParams): Promise<{
  items: TaskTypeData[];
  total: number;
}> {
  const query = new URLSearchParams();
  if (params.step_id !== undefined) query.set("step_id", String(params.step_id));
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  const queryString = query.toString();
  return apiRequest(`/api/v1/task-types${queryString ? `?${queryString}` : ""}`);
}

export async function createTaskType(payload: TaskTypePayload): Promise<TaskTypeData> {
  return apiRequest<TaskTypeData>("/api/v1/task-types", { method: "POST", body: payload });
}

export async function updateTaskType(id: string, payload: TaskTypePayload): Promise<TaskTypeData> {
  return apiRequest<TaskTypeData>(`/api/v1/task-types/${id}`, { method: "PUT", body: payload });
}

export async function deleteTaskType(id: string): Promise<void> {
  return apiRequest<void>(`/api/v1/task-types/${id}`, { method: "DELETE" });
}

export async function suggestTaskReward(
  complexity: TaskComplexity,
  duration: TaskDuration,
): Promise<{ reward: number }> {
  return apiRequest<{ reward: number }>("/api/v1/task-types/suggest-reward", {
    method: "POST",
    body: { complexity, duration },
  });
}

export async function transferTaskTypes(
  fromId: string,
  toId: string,
): Promise<{ transferred_count: number }> {
  return apiRequest("/api/v1/task-types/transfer", {
    method: "POST",
    body: { from_id: fromId, to_id: toId },
  });
}

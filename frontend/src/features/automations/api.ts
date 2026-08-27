import { apiRequest } from "@/lib/api";

export type TriggerKind =
  | "task.completed"
  | "lawsuit.stage_changed"
  | "lawsuit.created"
  | "publication.received"
  | "transaction.overdue";

export type ActionKind =
  "create_task" | "set_assignee" | "change_stage" | "notify" | "wait_condition";

export type DelayKind = "immediate" | "business_days" | "calendar_days" | "after_previous";

export interface AutomationActionData {
  id: string;
  position: number;
  action_kind: ActionKind;
  action_config: Record<string, unknown>;
  delay_kind: DelayKind;
  delay_value: number | null;
  condition: Record<string, unknown> | null;
}

export interface AutomationData {
  id: string;
  name: string;
  description: string | null;
  trigger_kind: TriggerKind;
  trigger_config: Record<string, unknown>;
  is_active: boolean;
  created_by: string;
  created_at: string;
  actions: AutomationActionData[];
}

export interface AutomationPayload {
  name: string;
  description?: string | null;
  trigger_kind: TriggerKind;
  trigger_config: Record<string, unknown>;
  actions: {
    action_kind: ActionKind;
    action_config: Record<string, unknown>;
    delay_kind: DelayKind;
    delay_value: number | null;
    condition: Record<string, unknown> | null;
  }[];
}

export interface SimulatedStepData {
  position: number;
  action_kind: ActionKind;
  status: "done" | "skipped" | "failed";
  detail: Record<string, unknown>;
  scheduled_for: string | null;
}

export interface TestResultData {
  steps: SimulatedStepData[];
  /** Sempre falso — a simulação não grava (spec 092, regra 10). */
  persisted: boolean;
}

export interface RunStepData {
  position: number;
  action_kind: ActionKind;
  status: "done" | "skipped" | "failed";
  detail: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
}

export interface RunData {
  id: string;
  automation_id: string;
  subject_type: string | null;
  subject_id: string | null;
  status: "running" | "waiting" | "done" | "failed";
  actions_completed: number;
  chain_depth: number;
  next_position: number | null;
  next_action_at: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  steps: RunStepData[];
}

export async function listAutomations(status?: "active" | "inactive") {
  const query = status ? `?status=${status}` : "";
  return apiRequest<{ items: AutomationData[]; total: number }>(`/api/v1/automations${query}`);
}

export async function createAutomation(payload: AutomationPayload): Promise<AutomationData> {
  return apiRequest<AutomationData>("/api/v1/automations", { method: "POST", body: payload });
}

export async function updateAutomation(
  id: string,
  payload: AutomationPayload,
): Promise<AutomationData> {
  return apiRequest<AutomationData>(`/api/v1/automations/${id}`, { method: "PUT", body: payload });
}

export async function deleteAutomation(id: string): Promise<void> {
  return apiRequest<void>(`/api/v1/automations/${id}`, { method: "DELETE" });
}

export async function toggleAutomation(id: string, isActive: boolean): Promise<AutomationData> {
  return apiRequest<AutomationData>(`/api/v1/automations/${id}/toggle`, {
    method: "POST",
    body: { is_active: isActive },
  });
}

export async function testAutomation(
  id: string,
  payload: Record<string, unknown>,
): Promise<TestResultData> {
  return apiRequest<TestResultData>(`/api/v1/automations/${id}/test`, {
    method: "POST",
    body: { payload },
  });
}

export async function listRuns(id: string): Promise<{ items: RunData[]; total: number }> {
  return apiRequest<{ items: RunData[]; total: number }>(`/api/v1/automations/${id}/runs`);
}

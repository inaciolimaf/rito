import { apiRequest } from "@/lib/api";

export type ActionStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "executed"
  | "failed"
  | "expired";

export interface ActionChange {
  before?: unknown;
  after?: unknown;
}

export interface ActionPreviewData {
  affected_type?: string;
  affected_id?: string | null;
  summary?: string;
  changes: Record<string, ActionChange>;
}

export interface AiActionData {
  id: string;
  thread_id: string | null;
  tool_name: string;
  status: ActionStatus;
  preview: ActionPreviewData;
  before_state: Record<string, unknown> | null;
  affected_type: string | null;
  affected_id: string | null;
  rejection_reason: string | null;
  error: string | null;
  expires_at: string;
  executed_at: string | null;
  undone_at: string | null;
  created_at: string;
}

export interface AuditEntryData {
  id: string;
  action_id: string;
  tool_name: string;
  affected_type: string;
  affected_id: string;
  before_state: Record<string, unknown> | null;
  after_state: Record<string, unknown> | null;
  model: string;
  thread_id: string | null;
  user_id: string;
  created_at: string;
}

interface Paged<T> {
  items: T[];
  total: number;
}

export async function listAiActions(status?: ActionStatus): Promise<Paged<AiActionData>> {
  const query = status ? `?status=${status}` : "";
  return apiRequest<Paged<AiActionData>>(`/api/v1/ai/actions${query}`);
}

export async function approveAiAction(id: string): Promise<AiActionData> {
  return apiRequest<AiActionData>(`/api/v1/ai/actions/${id}/approve`, { method: "POST" });
}

export async function rejectAiAction(id: string, reason?: string): Promise<AiActionData> {
  return apiRequest<AiActionData>(`/api/v1/ai/actions/${id}/reject`, {
    method: "POST",
    body: { reason: reason ?? null },
  });
}

export async function undoAiAction(id: string): Promise<AiActionData> {
  return apiRequest<AiActionData>(`/api/v1/ai/actions/${id}/undo`, { method: "POST" });
}

export async function listAiAudit(
  affectedType: string,
  affectedId: string,
): Promise<Paged<AuditEntryData>> {
  return apiRequest<Paged<AuditEntryData>>(
    `/api/v1/ai/audit?affected_type=${affectedType}&affected_id=${affectedId}`,
  );
}

import { apiRequest } from "@/lib/api";

export type ThreadStatus = "pending" | "running" | "waiting_human" | "done" | "error" | "cancelled";

export interface PendingActionData {
  kind: string;
  title: string;
  preview: Record<string, unknown>;
  description: string | null;
}

export interface ThreadData {
  id: string;
  graph_name: string;
  feature_key: string;
  title: string | null;
  status: ThreadStatus;
  context: Record<string, unknown>;
  pending_action: PendingActionData | null;
  output: Record<string, unknown> | null;
  error: string | null;
  step_count: number;
  user_id: string;
  waiting_since: string | null;
  created_at: string;
  updated_at: string;
}

export interface StepData {
  id: string;
  step: number;
  node: string;
  kind: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  duration_ms: number | null;
  error: string | null;
  created_at: string;
}

export interface StepListData {
  items: StepData[];
  total: number;
}

export interface CreateThreadPayload {
  graph_name: string;
  input?: Record<string, unknown>;
  context?: Record<string, unknown>;
  title?: string;
  autorun?: boolean;
}

export async function createThread(payload: CreateThreadPayload): Promise<ThreadData> {
  return apiRequest<ThreadData>("/api/v1/ai/threads", { method: "POST", body: payload });
}

export async function getThread(id: string): Promise<ThreadData> {
  return apiRequest<ThreadData>(`/api/v1/ai/threads/${id}`);
}

export async function listThreadSteps(id: string): Promise<StepListData> {
  return apiRequest<StepListData>(`/api/v1/ai/threads/${id}/steps`);
}

export async function resumeThread(
  id: string,
  approved: boolean,
  humanInput?: Record<string, unknown>,
): Promise<ThreadData> {
  return apiRequest<ThreadData>(`/api/v1/ai/threads/${id}/resume`, {
    method: "POST",
    body: { approved, human_input: humanInput ?? null },
  });
}

export async function cancelThread(id: string): Promise<ThreadData> {
  return apiRequest<ThreadData>(`/api/v1/ai/threads/${id}/cancel`, { method: "POST" });
}

import { apiRequest } from "@/lib/api";
import type { ActionPreviewData } from "@/features/ai/actions";

export interface CopilotContext {
  route?: string;
  lawsuit_id?: string;
  customer_id?: string;
  transaction_id?: string;
}

export interface PendingActionInline {
  action_id: string;
  kind: string;
  status: string;
  title: string;
  preview: ActionPreviewData;
}

export interface CopilotReply {
  thread_id: string;
  title: string | null;
  status: string;
  reply: string | null;
  pending_action: PendingActionInline | null;
  tool_labels: string[];
  model: string | null;
}

export interface CopilotThreadSummary {
  id: string;
  title: string | null;
  status: string;
  model: string | null;
  archived_at: string | null;
  updated_at: string;
  created_at: string;
}

export interface CopilotMessage {
  id: string;
  role: "user" | "assistant" | "tool" | "system";
  content: string | null;
  action_id: string | null;
  created_at: string;
}

export async function sendCopilotMessage(payload: {
  message: string;
  thread_id?: string;
  context?: CopilotContext;
  model?: string;
}): Promise<CopilotReply> {
  return apiRequest<CopilotReply>("/api/v1/ai/copilot/message", {
    method: "POST",
    body: payload,
  });
}

export async function listCopilotThreads(): Promise<{
  items: CopilotThreadSummary[];
  total: number;
}> {
  return apiRequest<{ items: CopilotThreadSummary[]; total: number }>("/api/v1/ai/copilot/threads");
}

export async function getCopilotThread(
  id: string,
): Promise<{ thread: CopilotThreadSummary; items: CopilotMessage[] }> {
  return apiRequest<{ thread: CopilotThreadSummary; items: CopilotMessage[] }>(
    `/api/v1/ai/copilot/threads/${id}`,
  );
}

export async function deleteCopilotThread(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/ai/copilot/threads/${id}`, { method: "DELETE" });
}

export async function listCopilotSuggestions(route: string): Promise<string[]> {
  const data = await apiRequest<{ items: string[] }>(
    `/api/v1/ai/copilot/suggestions?context=${encodeURIComponent(route)}`,
  );
  return data.items;
}

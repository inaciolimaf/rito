import { apiRequest } from "@/lib/api";

export interface AskResult {
  sql: string;
  relations: string[];
  touches_financial: boolean;
  executed: boolean;
  columns: string[];
  rows: Record<string, unknown>[];
  summary: string | null;
  query_id: string | null;
}

export interface InsightData {
  id: string;
  kind: "deadline_risk" | "stagnation" | "overdue" | "portfolio";
  severity: "info" | "warning" | "critical";
  subject_type: string | null;
  subject_id: string | null;
  title: string;
  body: string;
  suggested_action: Record<string, unknown> | null;
  dismissed_at: string | null;
  created_at: string;
}

export interface NextActionData {
  lawsuit_id: string;
  action: string;
  reason: string;
  signals: Record<string, unknown>;
  suggested_tool: string | null;
  suggested_arguments: Record<string, unknown>;
}

/** Primeira etapa: gera e valida o SQL, sem executar (spec 089, regra 3). */
export async function askMetrics(question: string): Promise<AskResult> {
  return apiRequest<AskResult>("/api/v1/ai/analytics/ask", {
    method: "POST",
    body: { question },
  });
}

/** Segunda etapa: o usuário viu o SQL e mandou rodar. */
export async function runMetrics(question: string, sql: string): Promise<AskResult> {
  return apiRequest<AskResult>("/api/v1/ai/analytics/ask", {
    method: "POST",
    body: { question, confirm_sql: sql },
  });
}

export async function listInsights(): Promise<{ items: InsightData[]; total: number }> {
  return apiRequest<{ items: InsightData[]; total: number }>("/api/v1/ai/insights");
}

export async function dismissInsight(id: string): Promise<InsightData> {
  return apiRequest<InsightData>(`/api/v1/ai/insights/${id}/dismiss`, { method: "POST" });
}

export async function refreshInsights(): Promise<{ created: number }> {
  return apiRequest<{ created: number }>("/api/v1/ai/insights/refresh", { method: "POST" });
}

export async function getNextBestAction(lawsuitId: string): Promise<NextActionData> {
  return apiRequest<NextActionData>(`/api/v1/lawsuits/${lawsuitId}/next-best-action`);
}

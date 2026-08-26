import { apiRequest } from "@/lib/api";

export interface PublicationAnalysisData {
  id: string;
  publication_id: string;
  summary: string;
  act_type: string | null;
  requires_action: boolean;
  deadline_days: number | null;
  deadline_kind: string | null;
  deadline_date: string | null;
  deadline_confidence: number | null;
  /** Falso quando a confiança é baixa: mostra o número, não preenche o campo. */
  should_prefill_deadline: boolean;
  suggested_task_type_id: string | null;
  suggested_user_id: string | null;
  reasoning: string | null;
  model: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  human_correction: Record<string, unknown> | null;
  created_at: string;
}

export async function analyzePublication(id: string): Promise<PublicationAnalysisData> {
  return apiRequest<PublicationAnalysisData>(`/api/v1/publications/${id}/analyze`, {
    method: "POST",
  });
}

export async function getPublicationAnalysis(id: string): Promise<PublicationAnalysisData> {
  return apiRequest<PublicationAnalysisData>(`/api/v1/publications/${id}/analysis`);
}

export interface ReviewPayload {
  approved: boolean;
  deadline_date?: string | null;
  task_type_id?: string | null;
  user_id?: string | null;
}

export async function reviewPublicationAnalysis(
  id: string,
  payload: ReviewPayload,
): Promise<{ analysis: PublicationAnalysisData; post_id: string | null }> {
  return apiRequest<{ analysis: PublicationAnalysisData; post_id: string | null }>(
    `/api/v1/publications/${id}/analysis/review`,
    { method: "POST", body: payload },
  );
}

export async function setAutoReadPublications(enabled: boolean): Promise<void> {
  await apiRequest<void>("/api/v1/account/ai-settings", {
    method: "PUT",
    body: { ai_auto_read_publications: enabled },
  });
}

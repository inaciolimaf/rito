import { apiRequest } from "@/lib/api";

/** Um campo lido do documento (spec 091, regras 3 e 4). `prefill` vem do servidor:
 * duas telas decidindo por conta própria o que é "confiança suficiente" seria a pior
 * forma de inconsistência. */
export interface ExtractionFieldData {
  value: string;
  confidence: number;
  prefill: boolean;
  is_valid: boolean;
}

export interface ExtractionDuplicateData {
  customer_id: string;
  name: string;
  identification: string | null;
}

export type ExtractionStatus = "pending" | "reviewed" | "applied" | "discarded";

export interface ExtractionData {
  id: string;
  filename: string;
  content_type: string;
  page_count: number | null;
  document_kind: string | null;
  target_type: string | null;
  used_ocr: boolean;
  ocr_text: string | null;
  fields: Record<string, ExtractionFieldData>;
  status: ExtractionStatus;
  action_id: string | null;
  applied_id: string | null;
  model: string | null;
  tokens_used: number | null;
  created_at: string;
  duplicate: ExtractionDuplicateData | null;
}

export async function extractDocument(file: File, expectedKind?: string): Promise<ExtractionData> {
  const form = new FormData();
  form.append("file", file);
  if (expectedKind) form.append("expected_kind", expectedKind);
  return apiRequest<ExtractionData>("/api/v1/documents/extract", { method: "POST", body: form });
}

export async function getExtraction(extractionId: string): Promise<ExtractionData> {
  return apiRequest<ExtractionData>(`/api/v1/documents/extractions/${extractionId}`);
}

export interface ApplyExtractionPayload {
  target_type: "customer" | "customer_update" | "lawsuit";
  arguments: Record<string, unknown>;
  corrections: Record<string, string>;
}

export async function applyExtraction(
  extractionId: string,
  payload: ApplyExtractionPayload,
): Promise<ExtractionData> {
  return apiRequest<ExtractionData>(`/api/v1/documents/extractions/${extractionId}/apply`, {
    method: "POST",
    body: payload,
  });
}

export async function discardExtraction(extractionId: string): Promise<ExtractionData> {
  return apiRequest<ExtractionData>(`/api/v1/documents/extractions/${extractionId}/discard`, {
    method: "POST",
  });
}

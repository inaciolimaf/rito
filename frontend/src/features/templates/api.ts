import type { ListResponse } from "@/components/domain/types";
import { apiRequest } from "@/lib/api";

export type TemplateType = "CONTRATO" | "PETICAO" | "RECURSO" | "DOCUMENTO";
export type TemplateView = "all" | "trash" | TemplateType;

export interface TemplateData {
  id: string;
  name: string;
  type: TemplateType;
  content: string;
  header_content: string;
  footer_content: string;
  watermark_text: string | null;
  created_by: string;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ListTemplatesParams {
  view?: TemplateView;
  q?: string;
  cursor?: string;
  limit?: number;
}

export async function listTemplates(
  params: ListTemplatesParams,
): Promise<ListResponse<TemplateData>> {
  const query = new URLSearchParams();
  if (params.view) query.set("view", params.view);
  if (params.q) query.set("q", params.q);
  if (params.cursor) query.set("cursor", params.cursor);
  if (params.limit) query.set("limit", String(params.limit));
  const queryString = query.toString();
  return apiRequest<ListResponse<TemplateData>>(
    `/api/v1/templates${queryString ? `?${queryString}` : ""}`,
  );
}

export interface TemplateFormPayload {
  name: string;
  type: TemplateType;
  content: string;
  header_content?: string;
  footer_content?: string;
  watermark_text?: string | null;
}

export async function getTemplate(id: string): Promise<TemplateData> {
  return apiRequest<TemplateData>(`/api/v1/templates/${id}`);
}

export async function createTemplate(values: TemplateFormPayload): Promise<TemplateData> {
  return apiRequest<TemplateData>("/api/v1/templates", { method: "POST", body: values });
}

export async function updateTemplate(
  id: string,
  values: TemplateFormPayload,
): Promise<TemplateData> {
  return apiRequest<TemplateData>(`/api/v1/templates/${id}`, { method: "PUT", body: values });
}

export async function deleteTemplate(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/templates/${id}`, { method: "DELETE" });
}

export async function restoreTemplate(id: string): Promise<TemplateData> {
  return apiRequest<TemplateData>(`/api/v1/templates/${id}/restore`, { method: "POST" });
}

export async function duplicateTemplate(id: string): Promise<TemplateData> {
  return apiRequest<TemplateData>(`/api/v1/templates/${id}/duplicate`, { method: "POST" });
}

export interface VariableCatalogItem {
  namespace: string;
  key: string;
  label: string;
}

export async function listTemplateVariables(): Promise<VariableCatalogItem[]> {
  return apiRequest<VariableCatalogItem[]>("/api/v1/template-variables");
}

export interface ResolveTemplateParams {
  customer_id?: string | null;
  lawsuit_id?: string | null;
}

export interface ResolvedTemplateData {
  content: string;
  header_content: string;
  footer_content: string;
  missing: string[];
}

/** Regra 7 (spec 066): nunca toca o modelo salvo — a resolução é sempre uma cópia,
 * consumida pela geração de documento (spec 067). */
export async function resolveTemplate(
  id: string,
  params: ResolveTemplateParams,
): Promise<ResolvedTemplateData> {
  return apiRequest<ResolvedTemplateData>(`/api/v1/templates/${id}/resolve`, {
    method: "POST",
    body: params,
  });
}

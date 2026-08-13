import type { ListResponse } from "@/components/domain/types";
import { apiRequest, apiRequestBlob } from "@/lib/api";

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

/** Regra 1 (spec 067): as 3 ações (baixar/enviar/salvar) partem do mesmo PDF —
 * `generateTemplatePdf` dispara o download no browser, mesmo padrão de
 * `exportCustomers`/`exportFinancialReport`. */
export async function generateTemplatePdf(
  id: string,
  params: ResolveTemplateParams,
  filename: string,
): Promise<void> {
  const blob = await apiRequestBlob(`/api/v1/templates/${id}/generate-pdf`, {
    method: "POST",
    body: params,
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export interface SaveToCloudParams {
  customer_id?: string | null;
  lawsuit_id: string;
}

export interface SavedDocumentData {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
}

export async function saveTemplateToCloud(
  id: string,
  params: SaveToCloudParams,
): Promise<SavedDocumentData> {
  return apiRequest<SavedDocumentData>(`/api/v1/templates/${id}/save-to-cloud`, {
    method: "POST",
    body: params,
  });
}

export interface SendTemplateEmailParams {
  customer_id?: string | null;
  lawsuit_id?: string | null;
  to: string;
  subject?: string;
}

export async function sendTemplateEmail(
  id: string,
  params: SendTemplateEmailParams,
): Promise<void> {
  await apiRequest<void>(`/api/v1/templates/${id}/send-email`, { method: "POST", body: params });
}

export interface PublicTemplateData {
  id: string;
  name: string;
  type: TemplateType;
  content: string;
  header_content: string;
  footer_content: string;
  watermark_text: string | null;
  created_at: string;
}

export async function listPublicTemplates(type?: TemplateType): Promise<PublicTemplateData[]> {
  const query = type ? `?type=${type}` : "";
  return apiRequest<PublicTemplateData[]>(`/api/v1/public-templates${query}`);
}

/** Regra 2/4 (spec 068): a cópia vira um `Template` comum do tenant, sem sufixo no
 * nome — editável dali em diante como qualquer modelo da biblioteca do escritório. */
export async function copyPublicTemplate(id: string): Promise<TemplateData> {
  return apiRequest<TemplateData>(`/api/v1/public-templates/${id}/copy`, { method: "POST" });
}

import { apiRequest, apiRequestBlob } from "@/lib/api";
import type { ListResponse } from "@/components/domain/types";

// Mesmo valor de PUBLICATIONS_TASK_TYPE_NAME (backend, app/domain/inbox/sections.py,
// spec 045) — a tarefa sistêmica que o roteamento de intimações cria. Dívida técnica
// #18 (docs/DIVIDA-TECNICA.md, spec 050): o cálculo de prazo real fica pra spec 086; até
// lá, essa tarefa nunca tem deadline_date preenchido — o front usa este nome pra
// distinguir "prazo não calculado" (regra 3 da 045) de "usuário não definiu prazo".
export const PUBLICATIONS_TASK_TYPE_NAME = "Intimações Judiciais";

export interface PublicationListItem {
  id: string;
  availability_date: string;
  court_code: string;
  organ_name: string | null;
  process_number: string | null;
  parties: string[];
  routed_to: string | null;
  routed_to_name: string | null;
  lawsuit_id: string | null;
  is_active: boolean;
  cancellation_reason: string | null;
  is_read: boolean;
}

export interface PublicationRecipient {
  name: string;
  pole: string | null;
}

export interface PublicationLawyer {
  name: string | null;
  oab_number: string | null;
  oab_state: string | null;
}

export interface PublicationDetail {
  id: string;
  external_id: number;
  availability_date: string;
  court_code: string;
  communication_type: string | null;
  document_type: string | null;
  organ_name: string | null;
  body: string;
  process_number: string | null;
  link: string | null;
  status: string | null;
  is_active: boolean;
  cancellation_reason: string | null;
  cancelled_at: string | null;
  lawsuit_id: string | null;
  post_id: string | null;
  matched_by: string | null;
  routed_to: string | null;
  routed_by: string | null;
  created_at: string;
  recipients: PublicationRecipient[];
  lawyers: PublicationLawyer[];
  is_read: boolean;
}

export interface PublicationCounts {
  total: number;
  unlinked: number;
  cancelled: number;
  unread: number;
}

export interface PublicationFilters {
  interval?: "today" | "3d" | "7d" | "custom";
  date_from?: string;
  date_to?: string;
  user_id?: string;
  customer_id?: string;
  court_code?: string;
  process_number?: string;
  linked?: boolean;
  cancelled?: boolean;
  read?: boolean;
}

function toQuery(params: object): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export async function listPublications(
  params: PublicationFilters & { cursor?: string; limit?: number },
): Promise<ListResponse<PublicationListItem>> {
  return apiRequest<ListResponse<PublicationListItem>>(`/api/v1/publications${toQuery(params)}`);
}

export async function getPublicationCounts(
  filters: PublicationFilters,
): Promise<PublicationCounts> {
  return apiRequest<PublicationCounts>(`/api/v1/publications/counts${toQuery(filters)}`);
}

export async function getPublication(id: string): Promise<PublicationDetail> {
  return apiRequest<PublicationDetail>(`/api/v1/publications/${id}`);
}

export async function markPublicationRead(id: string): Promise<PublicationDetail> {
  return apiRequest<PublicationDetail>(`/api/v1/publications/${id}/read`, {
    method: "POST",
    body: {},
  });
}

export async function linkPublicationToLawsuit(id: string, lawsuitId: string): Promise<void> {
  await apiRequest(`/api/v1/publications/${id}/link`, {
    method: "POST",
    body: { lawsuit_id: lawsuitId },
  });
}

/** Regra 9: respeita os filtros ativos, teto de 50.000 linhas — o backend decide. */
export async function exportPublications(
  format: "xlsx" | "pdf",
  filters: PublicationFilters,
): Promise<void> {
  const blob = await apiRequestBlob("/api/v1/publications/export", {
    method: "POST",
    body: { format, filters },
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `intimacoes.${format}`;
  link.click();
  URL.revokeObjectURL(url);
}

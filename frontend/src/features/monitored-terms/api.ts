import { apiRequest } from "@/lib/api";
import type { ListResponse } from "@/components/domain/types";

export type TermKind = "OAB" | "CPF" | "CNPJ";
export type TermStatus = "PENDENTE" | "SINCRONIZANDO" | "ATIVO" | "FALHA" | "PAUSADO";

export interface MonitoredTermData {
  id: string;
  kind: TermKind;
  value: string;
  oab_state: string | null;
  label: string | null;
  user_id: string | null;
  status: TermStatus;
  status_message: string | null;
  last_sync_at: string | null;
  last_success_at: string | null;
  next_sync_at: string | null;
  backfill_from: string | null;
  is_active: boolean;
  created_at: string;
  captured_count: number;
}

export interface TermSyncRunData {
  id: string;
  started_at: string;
  finished_at: string | null;
  found_count: number;
  new_count: number;
  error: string | null;
}

export interface ListMonitoredTermsParams {
  status?: TermStatus;
  kind?: TermKind;
  q?: string;
}

export async function listMonitoredTerms(
  params: ListMonitoredTermsParams,
): Promise<ListResponse<MonitoredTermData>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.kind) query.set("kind", params.kind);
  if (params.q) query.set("q", params.q);
  const queryString = query.toString();
  return apiRequest<ListResponse<MonitoredTermData>>(
    `/api/v1/monitored-terms${queryString ? `?${queryString}` : ""}`,
  );
}

export interface MonitoredTermPayload {
  kind: TermKind;
  value: string;
  oab_state?: string | null;
  label?: string | null;
  user_id?: string | null;
  backfill_from?: string | null;
}

export async function createMonitoredTerm(
  values: MonitoredTermPayload,
): Promise<MonitoredTermData> {
  return apiRequest<MonitoredTermData>("/api/v1/monitored-terms", {
    method: "POST",
    body: values,
  });
}

export async function updateMonitoredTerm(
  id: string,
  values: Pick<MonitoredTermPayload, "label" | "user_id" | "backfill_from"> & {
    is_active: boolean;
  },
): Promise<MonitoredTermData> {
  return apiRequest<MonitoredTermData>(`/api/v1/monitored-terms/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteMonitoredTerm(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/monitored-terms/${id}`, { method: "DELETE" });
}

export async function pauseMonitoredTerm(id: string): Promise<MonitoredTermData> {
  return apiRequest<MonitoredTermData>(`/api/v1/monitored-terms/${id}/pause`, {
    method: "POST",
  });
}

export async function resumeMonitoredTerm(id: string): Promise<MonitoredTermData> {
  return apiRequest<MonitoredTermData>(`/api/v1/monitored-terms/${id}/resume`, {
    method: "POST",
  });
}

export async function syncMonitoredTerm(id: string): Promise<TermSyncRunData> {
  return apiRequest<TermSyncRunData>(`/api/v1/monitored-terms/${id}/sync`, { method: "POST" });
}

export async function listTermSyncRuns(id: string): Promise<ListResponse<TermSyncRunData>> {
  return apiRequest<ListResponse<TermSyncRunData>>(`/api/v1/monitored-terms/${id}/runs`);
}

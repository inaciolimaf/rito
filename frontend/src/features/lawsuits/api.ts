import type { ListResponse } from "@/components/domain/types";
import { apiRequest, apiRequestBlob } from "@/lib/api";

export type PartyPoleApi = "ATIVO" | "PASSIVO" | "CONTRARIA" | "TERCEIRO";

export interface PartyInput {
  customer_id: string;
  pole: PartyPoleApi;
  is_client: boolean;
}

export interface PartyData {
  id: string;
  lawsuit_id: string;
  customer_id: string;
  customer_name: string;
  pole: PartyPoleApi;
  is_client: boolean;
  created_at: string;
}

export interface LawsuitData {
  id: string;
  user_id: string;
  lawsuit_type_id: string;
  action_group_id: string;
  action_group_name: string;
  stage_id: string;
  step_id: number;
  step_name: string;
  court_id: number | null;
  court_system_id: number | null;
  process_number: string | null;
  protocol_number: string | null;
  originating_process: string | null;
  folder: string | null;
  filing_year: number | null;
  judiciary: string | null;
  county: string | null;
  court_division: string | null;
  process_date: string | null;
  notes: string | null;
  case_value: number | null;
  fees_value: number | null;
  fees_percentage: number | null;
  contingency: "PROVAVEL" | "POSSIVEL" | "REMOTA" | null;
  closure_date: string | null;
  transit_date: string | null;
  archived_date: string | null;
  outcome: "GANHO" | "PERDIDO" | "ACORDO" | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface FinancialSummary {
  case_value: number | null;
  fees_value: number | null;
  received: number;
  to_receive: number;
  expenses: number;
  net_result: number;
}

export interface LawsuitFormPayload {
  user_id: string;
  lawsuit_type_id: string;
  stage_id: string;
  parties?: PartyInput[];
  court_id?: number | null;
  court_system_id?: number | null;
  process_number?: string | null;
  protocol_number?: string | null;
  originating_process?: string | null;
  folder?: string | null;
  filing_year?: number | null;
  judiciary?: string | null;
  county?: string | null;
  court_division?: string | null;
  process_date?: string | null;
  notes?: string | null;
  case_value?: number | null;
  fees_value?: number | null;
  fees_percentage?: number | null;
  contingency?: "PROVAVEL" | "POSSIVEL" | "REMOTA" | null;
  closure_date?: string | null;
  transit_date?: string | null;
  archived_date?: string | null;
  outcome?: "GANHO" | "PERDIDO" | "ACORDO" | null;
  is_archived?: boolean;
}

export async function getLawsuit(id: string): Promise<LawsuitData> {
  return apiRequest<LawsuitData>(`/api/v1/lawsuits/${id}`);
}

export async function createLawsuit(values: LawsuitFormPayload): Promise<LawsuitData> {
  return apiRequest<LawsuitData>("/api/v1/lawsuits", { method: "POST", body: values });
}

export async function updateLawsuit(id: string, values: LawsuitFormPayload): Promise<LawsuitData> {
  return apiRequest<LawsuitData>(`/api/v1/lawsuits/${id}`, { method: "PUT", body: values });
}

export async function deleteLawsuit(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/lawsuits/${id}`, { method: "DELETE" });
}

export async function listParties(lawsuitId: string): Promise<PartyData[]> {
  return apiRequest<PartyData[]>(`/api/v1/lawsuits/${lawsuitId}/parties`);
}

export async function getFinancialSummary(lawsuitId: string): Promise<FinancialSummary> {
  return apiRequest<FinancialSummary>(`/api/v1/lawsuits/${lawsuitId}/financial-summary`);
}

export interface ProcessNumberValidation {
  valid: boolean;
  formatted: string | null;
  parsed: {
    sequential: string;
    check_digit: string;
    year: number;
    segment: number;
    segment_name: string;
    court: string;
    origin: string;
  } | null;
  inferred_court: { id: number; code: string; name: string } | null;
  error: string | null;
}

export async function validateProcessNumber(rawDigits: string): Promise<ProcessNumberValidation> {
  return apiRequest<ProcessNumberValidation>("/api/v1/lawsuits/validate-number", {
    method: "POST",
    body: { process_number: rawDigits },
  });
}

export async function addParty(lawsuitId: string, party: PartyInput): Promise<PartyData> {
  return apiRequest<PartyData>(`/api/v1/lawsuits/${lawsuitId}/parties`, {
    method: "POST",
    body: party,
  });
}

export async function updateParty(
  lawsuitId: string,
  partyId: string,
  values: { pole: PartyPoleApi; is_client?: boolean },
): Promise<PartyData> {
  return apiRequest<PartyData>(`/api/v1/lawsuits/${lawsuitId}/parties/${partyId}`, {
    method: "PUT",
    body: values,
  });
}

export async function removeParty(lawsuitId: string, partyId: string): Promise<void> {
  await apiRequest<void>(`/api/v1/lawsuits/${lawsuitId}/parties/${partyId}`, {
    method: "DELETE",
  });
}

export type TimelineKind =
  "task" | "movement_auto" | "movement_manual" | "publication" | "transaction";

export interface TimelineItem {
  kind: TimelineKind;
  id: string;
  occurred_at: string;
  title: string;
  summary: string | null;
  actor: string | null;
  metadata: { header: string | null; external_code: number | null };
}

export interface TimelinePage {
  items: TimelineItem[];
  next_cursor: string | null;
  total: number;
}

export async function getTimeline(
  lawsuitId: string,
  params: { kinds: TimelineKind[]; cursor?: string; limit?: number },
): Promise<TimelinePage> {
  const query = new URLSearchParams();
  query.set("kinds", params.kinds.join(","));
  if (params.cursor) query.set("cursor", params.cursor);
  if (params.limit) query.set("limit", String(params.limit));
  return apiRequest<TimelinePage>(`/api/v1/lawsuits/${lawsuitId}/timeline?${query.toString()}`);
}

export interface MovementPayload {
  occurred_at: string;
  title: string;
  body?: string | null;
}

export interface MovementData {
  id: string;
  lawsuit_id: string;
  origin: "TRIBUNAL" | "MANUAL";
  occurred_at: string;
  title: string;
  body: string | null;
  header: string | null;
  external_code: number | null;
  external_id: string | null;
  created_by: string | null;
  created_at: string;
}

export async function createMovement(
  lawsuitId: string,
  values: MovementPayload,
): Promise<MovementData> {
  return apiRequest<MovementData>(`/api/v1/lawsuits/${lawsuitId}/movements`, {
    method: "POST",
    body: values,
  });
}

export async function updateMovement(
  lawsuitId: string,
  movementId: string,
  values: MovementPayload,
): Promise<MovementData> {
  return apiRequest<MovementData>(`/api/v1/lawsuits/${lawsuitId}/movements/${movementId}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteMovement(lawsuitId: string, movementId: string): Promise<void> {
  await apiRequest<void>(`/api/v1/lawsuits/${lawsuitId}/movements/${movementId}`, {
    method: "DELETE",
  });
}

export interface LawsuitListItem {
  id: string;
  process_number: string | null;
  folder: string | null;
  is_archived: boolean;
  created_at: string;
  last_movement_at: string | null;
  last_movement_title: string | null;
  lawsuit_type_name: string;
  action_group_name: string;
  stage_name: string;
  parties: { name: string; pole: string }[];
  parties_total: number;
}

export interface ListLawsuitsParams {
  view?: string;
  q?: string;
  stage_id?: string;
  customer_type?: string;
  archived?: boolean;
  created_from?: string;
  created_to?: string;
  cursor?: string;
  limit?: number;
}

export async function listLawsuits(
  params: ListLawsuitsParams,
): Promise<ListResponse<LawsuitListItem>> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const queryString = query.toString();
  return apiRequest<ListResponse<LawsuitListItem>>(
    `/api/v1/lawsuits${queryString ? `?${queryString}` : ""}`,
  );
}

/** Regra 10: export respeita os filtros ativos, não a página visível — mesmo padrão do
 * export de contatos (dispara o download no browser). */
export async function exportLawsuits(
  format: "xlsx" | "pdf",
  filters: ListLawsuitsParams,
): Promise<void> {
  const exportFilters = { ...filters };
  delete exportFilters.cursor;
  delete exportFilters.limit;
  const blob = await apiRequestBlob("/api/v1/lawsuits/export", {
    method: "POST",
    body: { format, filters: { view: "all", ...exportFilters } },
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `processos.${format}`;
  link.click();
  URL.revokeObjectURL(url);
}

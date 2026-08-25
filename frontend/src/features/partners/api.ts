import { apiRequest } from "@/lib/api";
/** As listas da parceria não paginam (regra 3: compartilhamento é processo a processo,
 * o volume é pequeno por definição) — daí `items`/`total` sem cursor. */
export interface PartnerList<T> {
  items: T[];
  total: number;
}

export type PartnershipStatus = "PENDENTE" | "ATIVA" | "RECUSADA" | "ENCERRADA";

export interface PartnershipData {
  id: string;
  status: PartnershipStatus;
  invited_email: string;
  partner_tenant_id: string | null;
  partner_name: string | null;
  is_requester: boolean;
  shared_count: number;
  accepted_at: string | null;
  created_at: string;
}

export interface PartnershipInviteResult {
  partnership: PartnershipData;
  account_exists: boolean;
  token: string;
}

export interface SharedLawsuitData {
  id: string;
  lawsuit_id: string;
  partnership_id: string;
  partner_tenant_id: string;
  partner_name: string | null;
  can_view_financial: boolean;
  can_create_tasks: boolean;
  revoked_at: string | null;
  created_at: string;
}

export interface SharedWithMeItem {
  share_id: string;
  lawsuit_id: string;
  partnership_id: string;
  owner_tenant_id: string;
  owner_name: string;
  process_number: string | null;
  folder: string | null;
  stage_name: string;
  step_id: number;
  can_view_financial: boolean;
  can_create_tasks: boolean;
  case_value: number | null;
  fees_value: number | null;
  open_tasks: number;
  shared_at: string;
}

export interface PartnershipSummary {
  shared_lawsuits: number;
  pending_by_office: number;
  pending_by_partner: number;
  active_partners: number;
}

export interface SharedWithMeResponse extends PartnerList<SharedWithMeItem> {
  report: { lawsuits_by_step: Record<string, number>; open_tasks: number } | null;
}

export async function listPartnerships(
  status?: PartnershipStatus,
): Promise<PartnerList<PartnershipData>> {
  const query = status ? `?status=${status}` : "";
  return apiRequest<PartnerList<PartnershipData>>(`/api/v1/partnerships${query}`);
}

export async function invitePartner(email: string): Promise<PartnershipInviteResult> {
  return apiRequest<PartnershipInviteResult>("/api/v1/partnerships/invite", {
    method: "POST",
    body: { email },
  });
}

export async function acceptPartnership(token: string): Promise<PartnershipData> {
  return apiRequest<PartnershipData>("/api/v1/partnerships/accept", {
    method: "POST",
    body: { token },
  });
}

export async function endPartnership(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/partnerships/${id}/end`, { method: "POST" });
}

export async function getPartnershipSummary(): Promise<PartnershipSummary> {
  return apiRequest<PartnershipSummary>("/api/v1/partnerships/summary");
}

export async function listSharedWithMe(steps?: number[]): Promise<SharedWithMeResponse> {
  const query = new URLSearchParams();
  for (const step of steps ?? []) query.append("steps", String(step));
  const queryString = query.toString();
  return apiRequest<SharedWithMeResponse>(
    `/api/v1/partnerships/shared-with-me${queryString ? `?${queryString}` : ""}`,
  );
}

export async function listLawsuitShares(
  lawsuitId: string,
): Promise<PartnerList<SharedLawsuitData>> {
  return apiRequest<PartnerList<SharedLawsuitData>>(`/api/v1/lawsuits/${lawsuitId}/shares`);
}

export interface ShareLawsuitPayload {
  partnership_id: string;
  can_view_financial: boolean;
  can_create_tasks: boolean;
}

export async function shareLawsuit(
  lawsuitId: string,
  payload: ShareLawsuitPayload,
): Promise<SharedLawsuitData> {
  return apiRequest<SharedLawsuitData>(`/api/v1/lawsuits/${lawsuitId}/share`, {
    method: "POST",
    body: payload,
  });
}

export async function revokeLawsuitShare(lawsuitId: string, shareId: string): Promise<void> {
  await apiRequest<void>(`/api/v1/lawsuits/${lawsuitId}/share/${shareId}`, { method: "DELETE" });
}

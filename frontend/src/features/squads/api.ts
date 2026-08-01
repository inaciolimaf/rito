import { apiRequest } from "@/lib/api";
import type { ListResponse } from "@/components/domain/types";

export interface SquadMember {
  id: string;
  name: string;
  avatar_url: string | null;
}

export interface SquadData {
  id: string;
  name: string;
  is_active: boolean;
  members: SquadMember[];
  created_at: string;
  updated_at: string;
}

export interface ListSquadsParams {
  status?: "active" | "inactive";
  q?: string;
  cursor?: string;
  limit?: number;
}

export async function listSquads(params: ListSquadsParams): Promise<ListResponse<SquadData>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  if (params.cursor) query.set("cursor", params.cursor);
  if (params.limit) query.set("limit", String(params.limit));

  const queryString = query.toString();
  return apiRequest<ListResponse<SquadData>>(
    `/api/v1/squads${queryString ? `?${queryString}` : ""}`,
  );
}

export async function getSquad(id: string): Promise<SquadData> {
  return apiRequest<SquadData>(`/api/v1/squads/${id}`);
}

export interface SquadFormPayload {
  name: string;
  is_active?: boolean;
  member_ids: string[];
}

export async function createSquad(values: SquadFormPayload): Promise<SquadData> {
  return apiRequest<SquadData>("/api/v1/squads", { method: "POST", body: values });
}

export async function updateSquad(id: string, values: SquadFormPayload): Promise<SquadData> {
  return apiRequest<SquadData>(`/api/v1/squads/${id}`, { method: "PUT", body: values });
}

export async function deleteSquad(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/squads/${id}`, { method: "DELETE" });
}

import { apiRequest } from "@/lib/api";
import type { ListResponse } from "@/components/domain/types";

export interface LawsuitTypeData {
  id: string;
  name: string;
  action_group_id: string;
  action_group_name: string;
  is_active: boolean;
  created_at: string;
}

export interface ListLawsuitTypesParams {
  group_id?: string;
  status?: "active" | "inactive";
  q?: string;
}

export async function listLawsuitTypes(
  params: ListLawsuitTypesParams,
): Promise<ListResponse<LawsuitTypeData>> {
  const query = new URLSearchParams();
  if (params.group_id) query.set("group_id", params.group_id);
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);

  const queryString = query.toString();
  return apiRequest<ListResponse<LawsuitTypeData>>(
    `/api/v1/lawsuit-types${queryString ? `?${queryString}` : ""}`,
  );
}

export interface LawsuitTypeFormPayload {
  name: string;
  action_group_id: string;
  is_active?: boolean;
}

export async function createLawsuitType(values: LawsuitTypeFormPayload): Promise<LawsuitTypeData> {
  return apiRequest<LawsuitTypeData>("/api/v1/lawsuit-types", { method: "POST", body: values });
}

export async function updateLawsuitType(
  id: string,
  values: LawsuitTypeFormPayload,
): Promise<LawsuitTypeData> {
  return apiRequest<LawsuitTypeData>(`/api/v1/lawsuit-types/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteLawsuitType(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/lawsuit-types/${id}`, { method: "DELETE" });
}

export async function transferLawsuitTypes(
  fromId: string,
  toId: string,
): Promise<{ transferred_count: number }> {
  return apiRequest<{ transferred_count: number }>("/api/v1/lawsuit-types/transfer", {
    method: "POST",
    body: { from_id: fromId, to_id: toId },
  });
}

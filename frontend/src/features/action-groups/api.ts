import { apiRequest } from "@/lib/api";
import type { ListResponse } from "@/components/domain/types";

export interface ActionGroupData {
  id: string;
  name: string;
  publications_user_id: string | null;
  is_active: boolean;
  lawsuit_types_count: number;
  created_at: string;
}

export interface ListActionGroupsParams {
  status?: "active" | "inactive";
  q?: string;
}

export async function listActionGroups(
  params: ListActionGroupsParams,
): Promise<ListResponse<ActionGroupData>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);

  const queryString = query.toString();
  return apiRequest<ListResponse<ActionGroupData>>(
    `/api/v1/action-groups${queryString ? `?${queryString}` : ""}`,
  );
}

export interface ActionGroupFormPayload {
  name: string;
  publications_user_id: string | null;
  is_active?: boolean;
}

export async function createActionGroup(values: ActionGroupFormPayload): Promise<ActionGroupData> {
  return apiRequest<ActionGroupData>("/api/v1/action-groups", { method: "POST", body: values });
}

export async function updateActionGroup(
  id: string,
  values: ActionGroupFormPayload,
): Promise<ActionGroupData> {
  return apiRequest<ActionGroupData>(`/api/v1/action-groups/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteActionGroup(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/action-groups/${id}`, { method: "DELETE" });
}

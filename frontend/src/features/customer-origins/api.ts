import { apiRequest } from "@/lib/api";
import type { ListResponse } from "@/components/domain/types";

export interface CustomerOriginData {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
}

export interface ListCustomerOriginsParams {
  status?: "active" | "inactive";
  q?: string;
}

export async function listCustomerOrigins(
  params: ListCustomerOriginsParams,
): Promise<ListResponse<CustomerOriginData>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);

  const queryString = query.toString();
  return apiRequest<ListResponse<CustomerOriginData>>(
    `/api/v1/customer-origins${queryString ? `?${queryString}` : ""}`,
  );
}

export interface CustomerOriginFormPayload {
  name: string;
  is_active?: boolean;
}

export async function createCustomerOrigin(
  values: CustomerOriginFormPayload,
): Promise<CustomerOriginData> {
  return apiRequest<CustomerOriginData>("/api/v1/customer-origins", {
    method: "POST",
    body: values,
  });
}

export async function updateCustomerOrigin(
  id: string,
  values: CustomerOriginFormPayload,
): Promise<CustomerOriginData> {
  return apiRequest<CustomerOriginData>(`/api/v1/customer-origins/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteCustomerOrigin(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/customer-origins/${id}`, { method: "DELETE" });
}

export async function transferCustomerOrigins(
  fromId: string,
  toId: string,
): Promise<{ transferred_count: number }> {
  return apiRequest<{ transferred_count: number }>("/api/v1/customer-origins/transfer", {
    method: "POST",
    body: { from_id: fromId, to_id: toId },
  });
}

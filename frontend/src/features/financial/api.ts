import type { ListResponse } from "@/components/domain/types";
import { apiRequest } from "@/lib/api";

export type EntryType = "RECEITA" | "DESPESA";

export interface DreGroupData {
  id: number;
  name: string;
  nature: EntryType;
}

export async function listDreGroups(): Promise<DreGroupData[]> {
  return apiRequest<DreGroupData[]>("/api/v1/dre-groups");
}

export interface FinancialCategoryData {
  id: string;
  name: string;
  type: EntryType;
  dre_group_id: number;
  dre_group_name: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ListFinancialCategoriesParams {
  type?: EntryType;
  group?: number;
  status?: "active" | "inactive";
  q?: string;
}

export async function listFinancialCategories(
  params: ListFinancialCategoriesParams,
): Promise<ListResponse<FinancialCategoryData>> {
  const query = new URLSearchParams();
  if (params.type) query.set("type", params.type);
  if (params.group !== undefined) query.set("group", String(params.group));
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  const queryString = query.toString();
  return apiRequest<ListResponse<FinancialCategoryData>>(
    `/api/v1/financial-categories${queryString ? `?${queryString}` : ""}`,
  );
}

export interface FinancialCategoryFormPayload {
  name: string;
  type: EntryType;
  dre_group_id: number;
  is_active?: boolean;
}

export async function createFinancialCategory(
  values: FinancialCategoryFormPayload,
): Promise<FinancialCategoryData> {
  return apiRequest<FinancialCategoryData>("/api/v1/financial-categories", {
    method: "POST",
    body: values,
  });
}

export async function updateFinancialCategory(
  id: string,
  values: FinancialCategoryFormPayload,
): Promise<FinancialCategoryData> {
  return apiRequest<FinancialCategoryData>(`/api/v1/financial-categories/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteFinancialCategory(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/financial-categories/${id}`, { method: "DELETE" });
}

export async function transferFinancialCategories(
  fromId: string,
  toId: string,
): Promise<{ transferred_count: number }> {
  return apiRequest<{ transferred_count: number }>("/api/v1/financial-categories/transfer", {
    method: "POST",
    body: { from_id: fromId, to_id: toId },
  });
}

export interface CostCenterData {
  id: string;
  name: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ListCostCentersParams {
  status?: "active" | "inactive";
  q?: string;
}

export async function listCostCenters(
  params: ListCostCentersParams,
): Promise<ListResponse<CostCenterData>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  const queryString = query.toString();
  return apiRequest<ListResponse<CostCenterData>>(
    `/api/v1/cost-centers${queryString ? `?${queryString}` : ""}`,
  );
}

export interface CostCenterFormPayload {
  name: string;
  is_active?: boolean;
}

export async function createCostCenter(values: CostCenterFormPayload): Promise<CostCenterData> {
  return apiRequest<CostCenterData>("/api/v1/cost-centers", { method: "POST", body: values });
}

export async function updateCostCenter(
  id: string,
  values: CostCenterFormPayload,
): Promise<CostCenterData> {
  return apiRequest<CostCenterData>(`/api/v1/cost-centers/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteCostCenter(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/cost-centers/${id}`, { method: "DELETE" });
}

export async function transferCostCenters(
  fromId: string,
  toId: string,
): Promise<{ transferred_count: number }> {
  return apiRequest<{ transferred_count: number }>("/api/v1/cost-centers/transfer", {
    method: "POST",
    body: { from_id: fromId, to_id: toId },
  });
}

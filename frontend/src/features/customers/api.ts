import type { ListResponse } from "@/components/domain/types";
import { apiRequest, apiRequestBlob } from "@/lib/api";

export interface CustomerData {
  id: string;
  type: "PF" | "PJ";
  name: string;
  identification: string | null;
  document: string | null;
  origin_id: string;
  notes: string | null;
  birthdate: string | null;
  marital_status_id: number | null;
  occupation: string | null;
  gender: string | null;
  nationality: string | null;
  mother_name: string | null;
  cellphone: string | null;
  phone: string | null;
  email: string | null;
  country: string;
  postal_code: string | null;
  state: string | null;
  city: string | null;
  street: string | null;
  region: string | null;
  number_pis: string | null;
  number_ctps: string | null;
  number_cid: string | null;
  photo_url: string | null;
  has_representative: boolean;
  rep_name: string | null;
  rep_identification: string | null;
  rep_document: string | null;
  rep_birthdate: string | null;
  rep_country: string | null;
  rep_state: string | null;
  rep_city: string | null;
  rep_street: string | null;
  rep_region: string | null;
  rep_postal_code: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface MaritalStatusData {
  id: number;
  name: string;
}

export async function listMaritalStatuses(): Promise<MaritalStatusData[]> {
  return apiRequest<MaritalStatusData[]>("/api/v1/marital-statuses");
}

export type CustomerFormPayload = Omit<
  CustomerData,
  "id" | "photo_url" | "is_archived" | "created_at" | "updated_at" | "marital_status_id"
> & {
  marital_status_id: number | null;
};

export async function createCustomer(values: CustomerFormPayload): Promise<CustomerData> {
  return apiRequest<CustomerData>("/api/v1/customers", { method: "POST", body: values });
}

export async function getCustomer(id: string): Promise<CustomerData> {
  return apiRequest<CustomerData>(`/api/v1/customers/${id}`);
}

export async function updateCustomer(
  id: string,
  values: CustomerFormPayload,
): Promise<CustomerData> {
  return apiRequest<CustomerData>(`/api/v1/customers/${id}`, { method: "PUT", body: values });
}

export async function archiveCustomer(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/customers/${id}`, { method: "DELETE" });
}

export async function uploadCustomerPhoto(id: string, file: File): Promise<CustomerData> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<CustomerData>(`/api/v1/customers/${id}/photo`, {
    method: "POST",
    body: formData,
  });
}

export interface DuplicateCandidate {
  id: string;
  name: string;
}

export interface CheckDuplicateResult {
  has_duplicate: boolean;
  candidates: DuplicateCandidate[];
}

/** Regra 9 (spec 018): aviso não bloqueante — nunca impede o submit, só informa. */
export async function checkDuplicateCustomer(
  name: string,
  birthdate: string,
): Promise<CheckDuplicateResult> {
  const params = new URLSearchParams({ name, birthdate });
  return apiRequest<CheckDuplicateResult>(`/api/v1/customers/check-duplicate?${params}`);
}

export interface CustomerListItem {
  id: string;
  type: "PF" | "PJ";
  name: string;
  cellphone: string | null;
  whatsapp_link: string | null;
  city: string | null;
  birthdate: string | null;
  is_archived: boolean;
  created_at: string;
}

export interface ListCustomersParams {
  q?: string;
  type?: "PF" | "PJ";
  state?: string;
  city?: string;
  origin_id?: string;
  created_from?: string;
  created_to?: string;
  has_active_lawsuit?: boolean;
  birthdays?: "day" | "month";
  archived?: boolean;
  sort?: "name" | "created_at";
  order?: "asc" | "desc";
  cursor?: string;
  limit?: number;
}

export async function listCustomers(
  params: ListCustomersParams,
): Promise<ListResponse<CustomerListItem>> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const queryString = query.toString();
  return apiRequest<ListResponse<CustomerListItem>>(
    `/api/v1/customers${queryString ? `?${queryString}` : ""}`,
  );
}

export interface CountedItem {
  name: string;
  count: number;
}

export interface CustomerStats {
  total: number;
  variation_vs_last_month: number;
  with_active_lawsuit: number;
  without_active_lawsuit: number;
  top_origins: CountedItem[];
  age_ranges: CountedItem[];
  top_occupations: CountedItem[];
}

export async function getCustomerStats(): Promise<CustomerStats> {
  return apiRequest<CustomerStats>("/api/v1/customers/stats");
}

export interface BirthdayItem {
  id: string;
  name: string;
  birthdate: string;
}

export async function getCustomerBirthdays(scope: "day" | "month"): Promise<BirthdayItem[]> {
  return apiRequest<BirthdayItem[]>(`/api/v1/customers/birthdays?scope=${scope}`);
}

export interface CustomerExportFilters {
  q?: string;
  type?: "PF" | "PJ";
  state?: string;
  city?: string;
  origin_id?: string;
  created_from?: string;
  created_to?: string;
  has_active_lawsuit?: boolean;
  birthdays?: "day" | "month";
  archived?: boolean;
}

/** Regra 7: respeita os filtros ativos, não a página visível. Dispara o download no
 * browser — não há uma tela de "arquivo pronto", o navegador que decide onde salvar. */
export async function exportCustomers(
  format: "xlsx" | "pdf",
  filters: CustomerExportFilters,
): Promise<void> {
  const blob = await apiRequestBlob("/api/v1/customers/export", {
    method: "POST",
    body: { format, filters },
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `contatos.${format}`;
  link.click();
  URL.revokeObjectURL(url);
}

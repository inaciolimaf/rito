import { apiRequest } from "@/lib/api";

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

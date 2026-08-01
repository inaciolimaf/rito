import { apiRequest } from "@/lib/api";
import type { ListResponse } from "@/components/domain/types";

export interface UserData {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  role: string;
  financial_access: string;
  occupation_id: number | null;
  identification: string | null;
  document: string | null;
  birthdate: string | null;
  number_ctps: string | null;
  number_oab: string | null;
  cellphone: string | null;
  phone: string | null;
  avatar_url: string | null;
  salary: string | null;
  admission_date: string | null;
  resignation_date: string | null;
  work_start: string | null;
  work_interval: string | null;
  work_end: string | null;
  points_goal: number | null;
  report_deadline: boolean;
  report_deleted: boolean;
  is_responsible: boolean;
  created_at: string;
  updated_at: string;
}

export interface Occupation {
  id: number;
  name: string;
}

export interface ListUsersParams {
  role?: string;
  status?: "active" | "inactive";
  q?: string;
  cursor?: string;
  limit?: number;
}

export async function listUsers(params: ListUsersParams): Promise<ListResponse<UserData>> {
  const query = new URLSearchParams();
  if (params.role) query.set("role", params.role);
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  if (params.cursor) query.set("cursor", params.cursor);
  if (params.limit) query.set("limit", String(params.limit));

  const queryString = query.toString();
  return apiRequest<ListResponse<UserData>>(`/api/v1/users${queryString ? `?${queryString}` : ""}`);
}

export async function getUser(id: string): Promise<UserData> {
  return apiRequest<UserData>(`/api/v1/users/${id}`);
}

export async function updateUser(id: string, values: Record<string, unknown>): Promise<UserData> {
  return apiRequest<UserData>(`/api/v1/users/${id}`, { method: "PUT", body: values });
}

export async function deactivateUser(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/users/${id}/deactivate`, { method: "POST" });
}

export async function uploadUserAvatar(id: string, file: File): Promise<UserData> {
  const formData = new FormData();
  formData.append("file", file);
  return apiRequest<UserData>(`/api/v1/users/${id}/avatar`, { method: "POST", body: formData });
}

export interface InviteUserValues {
  email: string;
  role: string;
  financial_access: string;
  occupation_id?: number;
}

export async function inviteUser(values: InviteUserValues): Promise<void> {
  await apiRequest<void>("/api/v1/users/invite", { method: "POST", body: values });
}

export async function getOccupations(): Promise<Occupation[]> {
  return apiRequest<Occupation[]>("/api/v1/occupations");
}

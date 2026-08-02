import { apiRequest } from "@/lib/api";

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
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface LawsuitFormPayload {
  user_id: string;
  lawsuit_type_id: string;
  stage_id: string;
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

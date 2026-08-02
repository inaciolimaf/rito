import { apiRequest } from "@/lib/api";

export type CourtSegment =
  | "ESTADUAL"
  | "FEDERAL"
  | "TRABALHO"
  | "ELEITORAL"
  | "MILITAR"
  | "SUPERIOR"
  | "CONTAS"
  | "CONSELHO";

export interface CourtData {
  id: number;
  code: string;
  name: string;
  segment: CourtSegment;
  state_code: string | null;
  datajud_alias: string | null;
  is_active: boolean;
}

export interface CourtSystemData {
  id: number;
  name: string;
}

export interface ListCourtsParams {
  q?: string;
  segment?: CourtSegment;
  state?: string;
}

export async function listCourts(params: ListCourtsParams = {}): Promise<CourtData[]> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  const queryString = query.toString();
  return apiRequest<CourtData[]>(`/api/v1/courts${queryString ? `?${queryString}` : ""}`);
}

export async function listCourtSystems(): Promise<CourtSystemData[]> {
  return apiRequest<CourtSystemData[]>("/api/v1/court-systems");
}

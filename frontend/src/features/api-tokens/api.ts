import { apiRequest } from "@/lib/api";

export interface ApiTokenData {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  allowed_ips: string[];
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  is_active: boolean;
  created_at: string;
  /** Regra 1: preenchido só na criação. Numa listagem é sempre nulo. */
  token: string | null;
}

export interface ScopeData {
  scope: string;
  description: string;
}

export interface ApiUsageRowData {
  path: string;
  method: string;
  calls: number;
  errors: number;
  avg_duration_ms: number | null;
}

export async function listApiTokens() {
  return apiRequest<{ items: ApiTokenData[]; total: number }>("/api/v1/api-tokens");
}

export async function listScopes(): Promise<ScopeData[]> {
  return apiRequest<ScopeData[]>("/api/v1/api-tokens/scopes");
}

export async function createApiToken(payload: {
  name: string;
  scopes: string[];
  allowed_ips: string[];
  expires_at?: string | null;
}): Promise<ApiTokenData> {
  return apiRequest<ApiTokenData>("/api/v1/api-tokens", { method: "POST", body: payload });
}

export async function revokeApiToken(id: string): Promise<ApiTokenData> {
  return apiRequest<ApiTokenData>(`/api/v1/api-tokens/${id}/revoke`, { method: "POST" });
}

export async function getApiUsage(days = 7) {
  return apiRequest<{ items: ApiUsageRowData[]; total_calls: number }>(
    `/api/v1/api-tokens/usage?days=${days}`,
  );
}

import { apiRequest } from "@/lib/api";

export interface StateData {
  code: string;
  name: string;
  ibge_code: number;
}

export interface CityData {
  ibge_code: number;
  name: string;
  state_code: string;
}

export async function listStates(): Promise<StateData[]> {
  return apiRequest<StateData[]>("/api/v1/states");
}

export async function listCities(stateCode: string, query?: string): Promise<CityData[]> {
  const params = new URLSearchParams({ state: stateCode });
  if (query) params.set("q", query);
  return apiRequest<CityData[]>(`/api/v1/cities?${params.toString()}`);
}

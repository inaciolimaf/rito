import { apiRequest } from "@/lib/api";

export type SearchFacet = "all" | "people" | "lawsuits";

export interface SearchHitData {
  id: string;
  label: string;
  sublabel: string | null;
  extra: Record<string, string>;
}

export interface FacetData {
  items: SearchHitData[];
  total: number;
}

export interface SearchResponseData {
  people: FacetData;
  lawsuits: FacetData;
  tasks: FacetData;
  took_ms: number;
  query_kind: string;
  recent: string[];
}

export async function search(
  query: string,
  facet: SearchFacet = "all",
): Promise<SearchResponseData> {
  const params = new URLSearchParams({ q: query, facet });
  return apiRequest<SearchResponseData>(`/api/v1/search?${params.toString()}`);
}

export async function listRecentSearches(): Promise<string[]> {
  const body = await apiRequest<{ items: string[] }>("/api/v1/search/recent");
  return body.items;
}

export async function recordSearchClick(payload: {
  query: string;
  type: string | null;
  id: string | null;
}): Promise<void> {
  return apiRequest<void>("/api/v1/search/click", { method: "POST", body: payload });
}

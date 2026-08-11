import { apiRequest } from "@/lib/api";

export interface BoardCard {
  id: string;
  process_number: string | null;
  folder: string | null;
  lawsuit_type_name: string;
  stage_id: string;
  stage_name: string;
  case_value: number | null;
  responsible_id: string;
  responsible_name: string;
  stage_entered_at: string;
  parties: { name: string; pole: string | null }[];
  parties_total: number;
}

export interface BoardColumn {
  step_id: number;
  step_name: string;
  total: number;
  items: BoardCard[];
}

export interface Board {
  columns: BoardColumn[];
  total: number;
  suggest_refine_filters: boolean;
}

export interface BoardColumnPage {
  items: BoardCard[];
  next_cursor: string | null;
  total: number;
}

export interface BoardFilters {
  view?: string;
  q?: string;
  action_group_id?: string;
  lawsuit_type_id?: string;
  user_id?: string;
  archived?: boolean;
}

function toQuery(params: object): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const queryString = query.toString();
  return queryString ? `?${queryString}` : "";
}

export async function getBoard(filters: BoardFilters = {}): Promise<Board> {
  return apiRequest<Board>(`/api/v1/crm/board${toQuery(filters)}`);
}

export async function getBoardColumn(
  stepId: number,
  params: BoardFilters & { cursor?: string; limit?: number } = {},
): Promise<BoardColumnPage> {
  return apiRequest<BoardColumnPage>(`/api/v1/crm/board/column/${stepId}${toQuery(params)}`);
}

export async function moveLawsuitStage(lawsuitId: string, stageId: string): Promise<void> {
  await apiRequest(`/api/v1/lawsuits/${lawsuitId}/move-stage`, {
    method: "POST",
    body: { stage_id: stageId },
  });
}

export async function bulkMoveLawsuitStage(
  lawsuitIds: string[],
  stageId: string,
): Promise<{ moved: number }> {
  return apiRequest<{ moved: number }>("/api/v1/lawsuits/bulk/move-stage", {
    method: "POST",
    body: { lawsuit_ids: lawsuitIds, stage_id: stageId },
  });
}

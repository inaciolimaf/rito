import type { ListResponse } from "@/components/domain/types";
import { apiRequest, apiRequestBlob } from "@/lib/api";
import type { RecurrencePeriod, RecurrenceWeek } from "@/features/posts/recurrence";

export interface AssigneeData {
  id: string;
  name: string;
}

export interface PostData {
  id: string;
  lawsuit_id: string;
  task_type_id: string;
  task_type_name: string;
  created_by: string;
  scheduled_date: string | null;
  scheduled_time: string | null;
  end_date: string | null;
  end_time: string | null;
  deadline_date: string | null;
  all_day: boolean;
  location: string | null;
  comments: string | null;
  reward_snapshot: number;
  is_important: boolean;
  is_urgent: boolean;
  is_future: boolean;
  is_private: boolean;
  show_in_schedule: boolean;
  all_completed: boolean;
  redacted: boolean;
  recurrence_id: string | null;
  assignees: AssigneeData[];
  created_at: string;
  updated_at: string;
}

export interface RecurrencePayload {
  period: RecurrencePeriod;
  repeat_on: RecurrenceWeek;
  until_date: string | null;
  max_occurrences: number | null;
}

export interface PostPayload {
  lawsuit_id: string;
  task_type_id: string;
  user_ids: string[];
  squad_id?: string | null;
  scheduled_date: string | null;
  scheduled_time: string | null;
  end_date: string | null;
  end_time: string | null;
  deadline_date: string | null;
  all_day: boolean;
  location: string | null;
  comments: string | null;
  is_important: boolean;
  is_urgent: boolean;
  is_future: boolean;
  is_private: boolean;
  show_in_schedule: boolean;
  recurrence?: RecurrencePayload | null;
}

export async function createPost(payload: PostPayload): Promise<PostData> {
  return apiRequest<PostData>("/api/v1/posts", { method: "POST", body: payload });
}

export async function getPost(postId: string): Promise<PostData> {
  return apiRequest<PostData>(`/api/v1/posts/${postId}`);
}

export async function listLawsuitPosts(lawsuitId: string): Promise<PostData[]> {
  return apiRequest<PostData[]>(`/api/v1/lawsuits/${lawsuitId}/posts`);
}

export async function completePost(postId: string, completedAt?: string): Promise<PostData> {
  return apiRequest<PostData>(`/api/v1/posts/${postId}/complete`, {
    method: "POST",
    body: completedAt ? { completed_at: completedAt } : {},
  });
}

export async function reopenPost(postId: string): Promise<PostData> {
  return apiRequest<PostData>(`/api/v1/posts/${postId}/reopen`, { method: "POST", body: {} });
}

/** A linha da tela de Atividades (spec 128) — o que cabe numa coluna, não o detalhe da
 * tarefa (`PostData`). */
export interface ActivityListItem {
  id: string;
  lawsuit_id: string;
  task_type_name: string;
  process_number: string | null;
  folder: string | null;
  scheduled_date: string | null;
  scheduled_time: string | null;
  deadline_date: string | null;
  is_important: boolean;
  is_urgent: boolean;
  is_private: boolean;
  status: "PENDENTE" | "CONCLUIDA" | "ATRASADA";
  assignee_names: string[];
  assignees_total: number;
  created_at: string;
}

export interface ActivityFilters {
  view?: "all" | "pending" | "completed" | "overdue";
  column?: "scheduled" | "deadline" | "created" | "completed";
  date_from?: string;
  date_to?: string;
  task_type_id?: string;
  lawsuit_id?: string;
  assignee_id?: string;
  sender?: "received" | "sent";
  /** CSV (`important,urgent`) — o backend lê a lista separada por vírgula. */
  priority?: string;
  include_future?: boolean;
}

export type ListActivitiesParams = ActivityFilters & {
  sort?: "scheduled_date" | "deadline_date" | "created_at";
  order?: "asc" | "desc";
  cursor?: string;
  limit?: number;
};

export async function listActivities(
  params: ListActivitiesParams,
): Promise<ListResponse<ActivityListItem>> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "" && value !== false) query.set(key, String(value));
  }
  const queryString = query.toString();
  return apiRequest<ListResponse<ActivityListItem>>(
    `/api/v1/posts${queryString ? `?${queryString}` : ""}`,
  );
}

/** Regra 7: exporta o FILTRO ativo, não a página visível. O navegador decide onde salvar. */
export async function exportActivities(
  format: "xlsx" | "pdf",
  filters: ActivityFilters,
): Promise<void> {
  const blob = await apiRequestBlob("/api/v1/posts/export", {
    method: "POST",
    body: { format, filters },
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `atividades.${format}`;
  link.click();
  URL.revokeObjectURL(url);
}

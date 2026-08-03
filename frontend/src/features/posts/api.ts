import { apiRequest } from "@/lib/api";
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

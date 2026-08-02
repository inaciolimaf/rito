import { apiRequest } from "@/lib/api";

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
  assignees: AssigneeData[];
  created_at: string;
  updated_at: string;
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
}

export async function createPost(payload: PostPayload): Promise<PostData> {
  return apiRequest<PostData>("/api/v1/posts", { method: "POST", body: payload });
}

export async function listLawsuitPosts(lawsuitId: string): Promise<PostData[]> {
  return apiRequest<PostData[]>(`/api/v1/lawsuits/${lawsuitId}/posts`);
}

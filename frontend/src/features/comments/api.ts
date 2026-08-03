import type { AttachmentData } from "@/features/attachments/api";
import { apiRequest } from "@/lib/api";

export interface CommentAuthor {
  id: string;
  name: string;
}

export interface CommentData {
  id: string;
  post_id: string;
  author: CommentAuthor;
  body: string | null;
  mentioned_user_ids: string[];
  attachments: AttachmentData[];
  deleted: boolean;
  created_at: string;
  updated_at: string;
}

export interface CommentPage {
  items: CommentData[];
  next_cursor: string | null;
  total: number;
}

export interface MentionableUser {
  id: string;
  name: string;
}

export async function listComments(postId: string, cursor?: string): Promise<CommentPage> {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiRequest<CommentPage>(`/api/v1/posts/${postId}/comments${query}`);
}

export async function createComment(postId: string, body: string): Promise<CommentData> {
  return apiRequest<CommentData>(`/api/v1/posts/${postId}/comments`, {
    method: "POST",
    body: { body },
  });
}

export async function updateComment(commentId: string, body: string): Promise<CommentData> {
  return apiRequest<CommentData>(`/api/v1/comments/${commentId}`, {
    method: "PUT",
    body: { body },
  });
}

export async function deleteComment(commentId: string): Promise<void> {
  return apiRequest<void>(`/api/v1/comments/${commentId}`, { method: "DELETE" });
}

/** Autocomplete de `@` (spec 035 §5) — usuários ativos do tenant, id + nome. */
export async function searchMentionableUsers(query: string): Promise<MentionableUser[]> {
  return apiRequest<MentionableUser[]>(`/api/v1/users/mentionable?q=${encodeURIComponent(query)}`);
}

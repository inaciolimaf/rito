import { apiRequest } from "@/lib/api";

export type InboxSectionKey =
  "deadline" | "publications" | "unread" | "urgent" | "important" | "others";

export const INBOX_SECTION_LABELS: Record<InboxSectionKey, string> = {
  deadline: "Prazo fatal",
  publications: "Intimações",
  unread: "Não lidas",
  urgent: "Urgentes",
  important: "Importantes",
  others: "Todas as demais",
};

export const DEFAULT_SECTION_ORDER: InboxSectionKey[] = [
  "deadline",
  "publications",
  "unread",
  "urgent",
  "important",
  "others",
];

export interface InboxRow {
  post_id: string;
  lawsuit_id: string;
  task_type_name: string;
  scheduled_date: string | null;
  scheduled_time: string | null;
  deadline_date: string | null;
  is_urgent: boolean;
  is_important: boolean;
  is_private: boolean;
  is_read: boolean;
  is_starred: boolean;
  created_at: string;
  parties: string[];
  assignee_names: string[];
}

export interface InboxPage {
  items: InboxRow[];
  next_cursor: string | null;
}

export type InboxCounts = Record<InboxSectionKey, number>;

export interface InboxPreferences {
  section_order: InboxSectionKey[];
  collapsed_sections: InboxSectionKey[];
  page_size: number;
}

export async function listInbox(section: InboxSectionKey, cursor?: string): Promise<InboxPage> {
  const query = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
  return apiRequest<InboxPage>(`/api/v1/inbox?section=${section}${query}`);
}

export async function getInboxCounts(): Promise<InboxCounts> {
  return apiRequest<InboxCounts>("/api/v1/inbox/counts");
}

export async function getInboxPreferences(): Promise<InboxPreferences> {
  return apiRequest<InboxPreferences>("/api/v1/inbox/preferences");
}

export async function putInboxPreferences(
  preferences: Pick<InboxPreferences, "section_order" | "collapsed_sections">,
): Promise<InboxPreferences> {
  return apiRequest<InboxPreferences>("/api/v1/inbox/preferences", {
    method: "PUT",
    body: preferences,
  });
}

async function bulkAction(
  action: "complete" | "read" | "star",
  postIds: string[],
  value?: boolean,
): Promise<void> {
  await apiRequest(`/api/v1/posts/bulk/${action}`, {
    method: "POST",
    body: value === undefined ? { post_ids: postIds } : { post_ids: postIds, value },
  });
}

export const bulkComplete = (postIds: string[]): Promise<void> => bulkAction("complete", postIds);
export const bulkRead = (postIds: string[], value = true): Promise<void> =>
  bulkAction("read", postIds, value);
export const bulkStar = (postIds: string[], value = true): Promise<void> =>
  bulkAction("star", postIds, value);

export async function bulkReassign(postIds: string[], toUserId: string): Promise<void> {
  await apiRequest("/api/v1/posts/bulk/reassign", {
    method: "POST",
    body: { post_ids: postIds, to_user_id: toUserId },
  });
}

import { apiRequest } from "@/lib/api";

export interface NotificationData {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPage {
  items: NotificationData[];
  next_cursor: string | null;
  total: number;
}

export async function listNotifications(unreadOnly: boolean): Promise<NotificationPage> {
  const query = unreadOnly ? "?unread=true" : "";
  return apiRequest<NotificationPage>(`/api/v1/notifications${query}`);
}

export async function markNotificationRead(notificationId: string): Promise<void> {
  await apiRequest(`/api/v1/notifications/${notificationId}/read`, { method: "POST", body: {} });
}

export async function markAllNotificationsRead(): Promise<void> {
  await apiRequest("/api/v1/notifications/read-all", { method: "POST", body: {} });
}

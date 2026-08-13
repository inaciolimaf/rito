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

export type NotificationEvent = "NOVO_CLIENTE" | "NOVO_PROCESSO" | "INTIMACAO";
export type NotificationChannel = "EMAIL" | "SMS" | "WHATSAPP";

export interface NotificationRuleData {
  event: NotificationEvent;
  responsible_user_id: string | null;
  channels: NotificationChannel[];
}

export interface NotificationPreferenceData {
  channel: NotificationChannel;
  enabled: boolean;
}

export async function listNotificationRules(): Promise<NotificationRuleData[]> {
  return apiRequest<NotificationRuleData[]>("/api/v1/notification-rules");
}

export async function updateNotificationRule(
  event: NotificationEvent,
  payload: { responsible_user_id: string | null; channels: NotificationChannel[] },
): Promise<NotificationRuleData> {
  return apiRequest<NotificationRuleData>(`/api/v1/notification-rules/${event}`, {
    method: "PUT",
    body: payload,
  });
}

export async function listNotificationPreferences(): Promise<NotificationPreferenceData[]> {
  return apiRequest<NotificationPreferenceData[]>("/api/v1/notification-preferences");
}

export async function updateNotificationPreference(
  channel: NotificationChannel,
  enabled: boolean,
): Promise<NotificationPreferenceData> {
  return apiRequest<NotificationPreferenceData>(`/api/v1/notification-preferences/${channel}`, {
    method: "PUT",
    body: { enabled },
  });
}

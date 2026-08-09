import { apiRequest } from "@/lib/api";

export type ScheduleStatus = "PENDENTE" | "CONCLUIDA" | "ATRASADA";
export type ScheduleDateField = "scheduled" | "deadline";

export interface ScheduleEvent {
  post_id: string;
  lawsuit_id: string;
  task_type_name: string;
  /** Eixo ativo (regra 2): scheduled_date ou deadline_date, conforme o filtro. */
  date: string;
  scheduled_date: string | null;
  scheduled_time: string | null;
  end_date: string | null;
  end_time: string | null;
  deadline_date: string | null;
  all_day: boolean;
  location: string | null;
  status: ScheduleStatus;
  is_urgent: boolean;
  is_important: boolean;
  assignee_names: string[];
}

export interface ListScheduleParams {
  from: string;
  to: string;
  userId?: string;
  dateField: ScheduleDateField;
  showCompleted: boolean;
}

export async function listSchedule(params: ListScheduleParams): Promise<ScheduleEvent[]> {
  const query = new URLSearchParams({ from: params.from, to: params.to });
  query.set("date_field", params.dateField);
  query.set("show_completed", String(params.showCompleted));
  if (params.userId) query.set("user_id", params.userId);
  const page = await apiRequest<{ items: ScheduleEvent[] }>(`/api/v1/schedule?${query}`);
  return page.items;
}

export interface ICalStatus {
  enabled: boolean;
  url: string | null;
}

export async function getIcalStatus(): Promise<ICalStatus> {
  return apiRequest<ICalStatus>("/api/v1/schedule/ical");
}

export async function enableIcal(): Promise<ICalStatus> {
  return apiRequest<ICalStatus>("/api/v1/schedule/ical/enable", { method: "POST" });
}

export async function regenerateIcal(): Promise<ICalStatus> {
  return apiRequest<ICalStatus>("/api/v1/schedule/ical/regenerate", { method: "POST" });
}

/** URL absoluta do feed para colar no Google Agenda — mesmo host da API. */
export function icalFullUrl(path: string): string {
  const base: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  return `${base}${path}`;
}

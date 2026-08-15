import { apiRequest } from "@/lib/api";

/** Camada de API da spec 071 — relatórios de Agilidade e Produtividade. */

export interface AgilityResponse {
  on_time: number;
  late: number;
  pending: number;
  avg_days_to_complete: number | null;
  avg_delay_days: number | null;
  staleness_hint: string;
}

export interface DelayedTaskItem {
  post_id: string;
  task_type_name: string;
  user_name: string;
  lawsuit_folder: string | null;
  deadline_date: string;
  completed_at_date: string;
  delay_days: number;
}

export interface DelayedUserItem {
  user_id: string;
  user_name: string;
  late_count: number;
  avg_delay_days: number;
}

export interface MostDelayedResponse {
  tasks: DelayedTaskItem[];
  users: DelayedUserItem[];
}

export interface ProductivityResponse {
  assigned: number;
  completed: number;
  late: number;
  due_in_5_days: number;
}

export interface WeeklyChartPoint {
  label: string;
  day: string;
  assigned: number;
  completed: number;
}

export interface WeeklyChartResponse {
  days: WeeklyChartPoint[];
}

export async function getAgilityReport(params: {
  from?: string;
  to?: string;
  userId?: string;
}): Promise<AgilityResponse> {
  const query = new URLSearchParams();
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.userId) query.set("user_id", params.userId);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<AgilityResponse>(`/api/v1/reports/agility${suffix}`);
}

export async function getMostDelayedReport(limit = 10): Promise<MostDelayedResponse> {
  return apiRequest<MostDelayedResponse>(`/api/v1/reports/most-delayed?limit=${limit}`);
}

export async function getProductivityReport(params: {
  month?: string;
  userId?: string;
}): Promise<ProductivityResponse> {
  const query = new URLSearchParams();
  if (params.month) query.set("month", params.month);
  if (params.userId) query.set("user_id", params.userId);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<ProductivityResponse>(`/api/v1/reports/productivity${suffix}`);
}

export async function getProductivityWeeklyReport(userId?: string): Promise<WeeklyChartResponse> {
  const suffix = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
  return apiRequest<WeeklyChartResponse>(`/api/v1/reports/productivity/weekly${suffix}`);
}

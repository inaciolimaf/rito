import { apiRequest, apiRequestBlob } from "@/lib/api";

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

/** Camada de API da spec 072 — os 9 relatórios tabulares, servidos por uma única rota
 * genérica dirigida por `report_key` (regra 1). */

export type ReportKey =
  | "productivity"
  | "delayed_tasks"
  | "access_logs"
  | "new_customers"
  | "new_lawsuits"
  | "won_lawsuits"
  | "lost_lawsuits"
  | "hearings"
  | "contrary_parties";

export interface ProductivityTableRow {
  post_id: string;
  responsible_name: string;
  customer_name: string | null;
  task_type_name: string;
  points: number;
  scheduled_date: string | null;
  completed_at: string | null;
}

export interface DelayedTaskTableRow {
  post_id: string;
  responsible_name: string;
  customer_name: string | null;
  task_type_name: string;
  points: number;
  scheduled_date: string | null;
  delay_days: number;
}

export interface AccessLogTableRow {
  user_id: string;
  user_name: string;
  day: string;
  ip_address: string | null;
  first_login: string;
  last_login: string;
}

export interface NewCustomerTableRow {
  customer_id: string;
  name: string;
  contact: string | null;
  city_state: string | null;
  origin_name: string | null;
  created_at: string;
}

export interface NewLawsuitTableRow {
  lawsuit_id: string;
  parties: string;
  lawsuit_type_name: string;
  process_number: string | null;
  responsible_name: string;
  created_at: string;
}

export interface LawsuitOutcomeTableRow {
  lawsuit_id: string;
  parties: string;
  lawsuit_type_name: string;
  process_number: string | null;
  fees_value: string | null;
  closure_date: string;
  total_days: number;
}

export interface HearingTableRow {
  post_id: string;
  scheduled_date: string;
  scheduled_time: string | null;
  task_type_name: string;
  process_number: string | null;
  parties: string;
  location: string | null;
  responsible_name: string | null;
}

export interface ContraryPartyTableRow {
  customer_id: string;
  name: string;
  identification: string | null;
  city: string | null;
  lawsuit_count: number;
}

export type ReportTableRow =
  | ProductivityTableRow
  | DelayedTaskTableRow
  | AccessLogTableRow
  | NewCustomerTableRow
  | NewLawsuitTableRow
  | LawsuitOutcomeTableRow
  | HearingTableRow
  | ContraryPartyTableRow;

export interface ReportListResponse<T> {
  items: T[];
  next_cursor: string | null;
  total: number;
  points_total: number | null;
  disabled_reason: string | null;
}

export interface TabularReportParams {
  from?: string;
  to?: string;
  user_id?: string;
  action_group_id?: string;
  cursor?: string;
  limit?: number;
}

function buildTabularQuery(params: TabularReportParams): string {
  const query = new URLSearchParams();
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.user_id) query.set("user_id", params.user_id);
  if (params.action_group_id) query.set("action_group_id", params.action_group_id);
  if (params.cursor) query.set("cursor", params.cursor);
  if (params.limit) query.set("limit", String(params.limit));
  return query.toString();
}

export async function getTabularReport<T = ReportTableRow>(
  reportKey: ReportKey,
  params: TabularReportParams,
): Promise<ReportListResponse<T>> {
  const query = buildTabularQuery(params);
  const suffix = query ? `?${query}` : "";
  return apiRequest<ReportListResponse<T>>(`/api/v1/reports/tabular/${reportKey}${suffix}`);
}

/** Camada de API da spec 073 — livro de ponto. */

export interface TimesheetDayData {
  day: string;
  first_access: string | null;
  last_access: string | null;
  access_count: number;
  deviation_minutes: number | null;
  is_weekend: boolean;
  is_holiday: boolean;
}

export interface TimesheetData {
  user_id: string;
  month: string;
  days: TimesheetDayData[];
}

export async function getTimesheet(params: {
  month?: string;
  userId?: string;
}): Promise<TimesheetData> {
  const query = new URLSearchParams();
  if (params.month) query.set("month", params.month);
  if (params.userId) query.set("user_id", params.userId);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<TimesheetData>(`/api/v1/reports/timesheet${suffix}`);
}

export async function exportTimesheet(params: { month?: string; userId?: string }): Promise<void> {
  const query = new URLSearchParams();
  if (params.month) query.set("month", params.month);
  if (params.userId) query.set("user_id", params.userId);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const blob = await apiRequestBlob(`/api/v1/reports/timesheet/export${suffix}`, {
    method: "POST",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "timesheet.xlsx";
  link.click();
  URL.revokeObjectURL(url);
}

export async function exportTabularReport(
  reportKey: ReportKey,
  format: "xlsx" | "pdf",
  params: TabularReportParams,
): Promise<void> {
  const query = buildTabularQuery(params);
  const blob = await apiRequestBlob(
    `/api/v1/reports/tabular/${reportKey}/export?format=${format}${query ? `&${query}` : ""}`,
    { method: "POST" },
  );
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${reportKey}.${format}`;
  link.click();
  URL.revokeObjectURL(url);
}

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

/** Camada de API da spec 074 — BI: Estoque e Prospecção (funil comercial). */

export interface ClosedMonthCardData {
  value: number;
  delta_pct: number | null;
  previous: number;
}

export interface ClosedTrendPointData {
  month: string;
  closed: number;
}

export interface BiPipelineData {
  opportunities_month: number;
  active: number;
  archived: number;
  idle_120: number;
  closed_month: ClosedMonthCardData;
  in_service: number;
  closed_trend: ClosedTrendPointData[];
  staleness_hint: string;
  crm_warning: string;
}

export interface ConversionGroupData {
  action_group_id: string;
  action_group_name: string;
  opportunities: number;
  closed: number;
  /** Regra 11: null = "—" na UI, nunca 0% quando não há oportunidades. */
  conversion_rate: number | null;
}

export interface BiConversionData {
  period: string;
  groups: ConversionGroupData[];
  staleness_hint: string;
}

export interface PortfolioStepItemData {
  step_id: number;
  step_name: string;
  active: number;
}

export interface PortfolioPeriodItemData {
  month: string;
  active: number;
}

export type PortfolioGroupBy = "step" | "period";

export type BiPortfolioData =
  | { group_by: "step"; items: PortfolioStepItemData[] }
  | { group_by: "period"; items: PortfolioPeriodItemData[] };

export interface BiPipelineParams {
  from?: string;
  to?: string;
  actionGroupId?: string;
}

function buildBiQuery(params: BiPipelineParams): string {
  const query = new URLSearchParams();
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.actionGroupId) query.set("action_group_id", params.actionGroupId);
  const text = query.toString();
  return text ? `?${text}` : "";
}

export async function getBiPipeline(params: BiPipelineParams): Promise<BiPipelineData> {
  return apiRequest<BiPipelineData>(`/api/v1/bi/pipeline${buildBiQuery(params)}`);
}

export async function getBiConversion(period?: string): Promise<BiConversionData> {
  const suffix = period ? `?period=${encodeURIComponent(period)}` : "";
  return apiRequest<BiConversionData>(`/api/v1/bi/pipeline/conversion${suffix}`);
}

export async function getBiPortfolio(
  groupBy: PortfolioGroupBy,
  params: BiPipelineParams = {},
): Promise<BiPortfolioData> {
  const query = new URLSearchParams();
  query.set("group_by", groupBy);
  if (params.actionGroupId) query.set("action_group_id", params.actionGroupId);
  return apiRequest<BiPortfolioData>(`/api/v1/bi/pipeline/portfolio?${query.toString()}`);
}

/** Camada de API da spec 075 — BI: Safra e Qualidade. */

export interface VintageYearData {
  vintage_year: number;
  total: number;
  won: number;
  lost: number;
  settled: number;
  in_progress: number;
  transited: number;
  archived: number;
  /** Regra 7: média só entre arquivados — null quando a safra não tem nenhum. */
  avg_cycle_days: number | null;
  /** Regra 11: null = "—" na UI, nunca 0% quando não há concluídos. */
  success_rate: number | null;
  /** Regra 5: menos de 10 concluídos na safra. */
  small_sample: boolean;
  /** Regra 9: variação vs safra anterior; null na primeira safra. */
  rate_change_pp: number | null;
  highlighted: boolean;
}

export interface BiVintageData {
  years: VintageYearData[];
  staleness_hint: string;
}

export interface SuccessRateGroupData {
  action_group_id: string;
  action_group_name: string;
  won: number;
  lost: number;
  settled: number;
  concluded: number;
  /** Regra 11: null = "—" na UI, nunca 0% quando não há concluídos. */
  success_rate: number | null;
  small_sample: boolean;
}

export interface BiSuccessRateData {
  period: string;
  groups: SuccessRateGroupData[];
  /** Regra 2: o critério da taxa, explicado no tooltip da UI. */
  rate_note: string;
}

export interface SuccessTrendPointData {
  month: string;
  won: number;
  lost: number;
  settled: number;
  concluded: number;
  /** Mês sem concluído → null ("—"), nunca 0%. */
  success_rate: number | null;
}

export interface BiSuccessTrendData {
  months: number;
  points: SuccessTrendPointData[];
  rate_note: string;
}

export interface BiVintageParams {
  fromYear?: number;
  toYear?: number;
  actionGroupId?: string;
}

export async function getBiVintage(params: BiVintageParams = {}): Promise<BiVintageData> {
  const query = new URLSearchParams();
  if (params.fromYear) query.set("from_year", String(params.fromYear));
  if (params.toYear) query.set("to_year", String(params.toYear));
  if (params.actionGroupId) query.set("action_group_id", params.actionGroupId);
  const text = query.toString();
  return apiRequest<BiVintageData>(`/api/v1/bi/vintage${text ? `?${text}` : ""}`);
}

export async function getBiSuccessRate(
  params: {
    period?: string;
    actionGroupId?: string;
  } = {},
): Promise<BiSuccessRateData> {
  const query = new URLSearchParams();
  if (params.period) query.set("period", params.period);
  if (params.actionGroupId) query.set("action_group_id", params.actionGroupId);
  const text = query.toString();
  return apiRequest<BiSuccessRateData>(`/api/v1/bi/success-rate${text ? `?${text}` : ""}`);
}

export async function getBiSuccessTrend(
  params: {
    actionGroupId?: string;
    months?: number;
  } = {},
): Promise<BiSuccessTrendData> {
  const query = new URLSearchParams();
  if (params.actionGroupId) query.set("action_group_id", params.actionGroupId);
  if (params.months) query.set("months", String(params.months));
  const text = query.toString();
  return apiRequest<BiSuccessTrendData>(`/api/v1/bi/success-rate/trend${text ? `?${text}` : ""}`);
}

/** Camada de API da spec 076 — BI: Tempo e Honorários. */

export interface CycleAveragesData {
  /** Regra 2: null = "não sei" (data faltando), nunca zero — zero é "no mesmo dia". */
  prospecting_days: number | null;
  production_days: number | null;
  execution_days: number | null;
  full_cycle_days: number | null;
}

export interface BiTimeFeesData {
  lawsuits: number;
  /** Regra 3: soma de fees_value ÷ processos no filtro; null = recorte vazio ("—"). */
  avg_fees: number | null;
  /** Regra 4: média de (honorários ÷ meses de duração); null quando nenhum processo
   * do recorte tem rotação completa maior que zero. */
  avg_monthly_fees: number | null;
  cycles: CycleAveragesData;
  staleness_hint: string;
}

export interface TimeFeesGroupData {
  action_group_id: string;
  action_group_name: string;
  lawsuits: number;
  cycles: CycleAveragesData;
}

export interface BiTimeFeesByGroupData {
  groups: TimeFeesGroupData[];
  staleness_hint: string;
}

export interface TimeFeesTypeData {
  lawsuit_type_id: string;
  lawsuit_type_name: string;
  lawsuits: number;
  /** Regra 8: média de (fees_value ÷ meses) dos processos do tipo; null → "—". */
  monthly_profitability: number | null;
  /** Regra 9: menos de 5 processos no recorte. */
  small_sample: boolean;
}

export interface BiTimeFeesByTypeData {
  types: TimeFeesTypeData[];
  staleness_hint: string;
}

export interface BiLostTimeData {
  /** Regra 5: processos sem receita paga com rotação completa maior que zero. */
  zero_revenue_lawsuits: number;
  lost_months: number;
  staleness_hint: string;
}

export interface BiTimeFeesParams {
  outcome?: string;
  from?: string;
  to?: string;
  actionGroupId?: string;
}

export async function getBiTimeFees(params: BiTimeFeesParams = {}): Promise<BiTimeFeesData> {
  const query = new URLSearchParams();
  if (params.outcome) query.set("outcome", params.outcome);
  if (params.from) query.set("from", params.from);
  if (params.to) query.set("to", params.to);
  if (params.actionGroupId) query.set("action_group_id", params.actionGroupId);
  const text = query.toString();
  return apiRequest<BiTimeFeesData>(`/api/v1/bi/time-fees${text ? `?${text}` : ""}`);
}

export async function getBiTimeFeesByGroup(): Promise<BiTimeFeesByGroupData> {
  return apiRequest<BiTimeFeesByGroupData>("/api/v1/bi/time-fees/by-group");
}

export async function getBiTimeFeesByType(lawsuitTypeId?: string): Promise<BiTimeFeesByTypeData> {
  const suffix = lawsuitTypeId ? `?lawsuit_type_id=${encodeURIComponent(lawsuitTypeId)}` : "";
  return apiRequest<BiTimeFeesByTypeData>(`/api/v1/bi/time-fees/by-type${suffix}`);
}

export async function getBiLostTime(): Promise<BiLostTimeData> {
  return apiRequest<BiLostTimeData>("/api/v1/bi/time-fees/lost-time");
}

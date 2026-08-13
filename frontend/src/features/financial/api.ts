import type { ListResponse } from "@/components/domain/types";
import type { AttachmentData } from "@/features/attachments/api";
import { apiRequest, apiRequestBlob } from "@/lib/api";

export type EntryType = "RECEITA" | "DESPESA";

export interface DreGroupData {
  id: number;
  name: string;
  nature: EntryType;
}

export async function listDreGroups(): Promise<DreGroupData[]> {
  return apiRequest<DreGroupData[]>("/api/v1/dre-groups");
}

export interface FinancialCategoryData {
  id: string;
  name: string;
  type: EntryType;
  dre_group_id: number;
  dre_group_name: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ListFinancialCategoriesParams {
  type?: EntryType;
  group?: number;
  status?: "active" | "inactive";
  q?: string;
}

export async function listFinancialCategories(
  params: ListFinancialCategoriesParams,
): Promise<ListResponse<FinancialCategoryData>> {
  const query = new URLSearchParams();
  if (params.type) query.set("type", params.type);
  if (params.group !== undefined) query.set("group", String(params.group));
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  const queryString = query.toString();
  return apiRequest<ListResponse<FinancialCategoryData>>(
    `/api/v1/financial-categories${queryString ? `?${queryString}` : ""}`,
  );
}

export interface FinancialCategoryFormPayload {
  name: string;
  type: EntryType;
  dre_group_id: number;
  is_active?: boolean;
}

export async function createFinancialCategory(
  values: FinancialCategoryFormPayload,
): Promise<FinancialCategoryData> {
  return apiRequest<FinancialCategoryData>("/api/v1/financial-categories", {
    method: "POST",
    body: values,
  });
}

export async function updateFinancialCategory(
  id: string,
  values: FinancialCategoryFormPayload,
): Promise<FinancialCategoryData> {
  return apiRequest<FinancialCategoryData>(`/api/v1/financial-categories/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteFinancialCategory(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/financial-categories/${id}`, { method: "DELETE" });
}

export async function transferFinancialCategories(
  fromId: string,
  toId: string,
): Promise<{ transferred_count: number }> {
  return apiRequest<{ transferred_count: number }>("/api/v1/financial-categories/transfer", {
    method: "POST",
    body: { from_id: fromId, to_id: toId },
  });
}

export interface CostCenterData {
  id: string;
  name: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ListCostCentersParams {
  status?: "active" | "inactive";
  q?: string;
}

export async function listCostCenters(
  params: ListCostCentersParams,
): Promise<ListResponse<CostCenterData>> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.q) query.set("q", params.q);
  const queryString = query.toString();
  return apiRequest<ListResponse<CostCenterData>>(
    `/api/v1/cost-centers${queryString ? `?${queryString}` : ""}`,
  );
}

export interface CostCenterFormPayload {
  name: string;
  is_active?: boolean;
}

export async function createCostCenter(values: CostCenterFormPayload): Promise<CostCenterData> {
  return apiRequest<CostCenterData>("/api/v1/cost-centers", { method: "POST", body: values });
}

export async function updateCostCenter(
  id: string,
  values: CostCenterFormPayload,
): Promise<CostCenterData> {
  return apiRequest<CostCenterData>(`/api/v1/cost-centers/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteCostCenter(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/cost-centers/${id}`, { method: "DELETE" });
}

export async function transferCostCenters(
  fromId: string,
  toId: string,
): Promise<{ transferred_count: number }> {
  return apiRequest<{ transferred_count: number }>("/api/v1/cost-centers/transfer", {
    method: "POST",
    body: { from_id: fromId, to_id: toId },
  });
}

export type AccountKind = "CORRENTE" | "POUPANCA" | "INVESTIMENTO" | "CARTAO_CREDITO" | "OUTRO";

export interface FinancialInstitutionData {
  id: number;
  name: string;
  compe_code: string | null;
}

export async function listFinancialInstitutions(q?: string): Promise<FinancialInstitutionData[]> {
  const query = q ? `?q=${encodeURIComponent(q)}` : "";
  const body = await apiRequest<{ items: FinancialInstitutionData[] }>(
    `/api/v1/financial-institutions${query}`,
  );
  return body.items;
}

export interface BankAccountData {
  id: string;
  kind: AccountKind;
  name: string;
  institution_id: number | null;
  institution_name: string | null;
  agency: string | null;
  account_number: string | null;
  cycle_day: number | null;
  due_day: number | null;
  initial_amount: number;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
}

export interface ListBankAccountsParams {
  kind?: AccountKind;
  status?: "active" | "inactive";
}

export async function listBankAccounts(
  params: ListBankAccountsParams,
): Promise<ListResponse<BankAccountData>> {
  const query = new URLSearchParams();
  if (params.kind) query.set("kind", params.kind);
  if (params.status) query.set("status", params.status);
  const queryString = query.toString();
  return apiRequest<ListResponse<BankAccountData>>(
    `/api/v1/bank-accounts${queryString ? `?${queryString}` : ""}`,
  );
}

export interface BankAccountFormPayload {
  kind: AccountKind;
  name: string;
  institution_id?: number | null;
  agency?: string | null;
  account_number?: string | null;
  cycle_day?: number | null;
  due_day?: number | null;
  initial_amount: string;
  is_default?: boolean;
  is_active?: boolean;
}

export async function createBankAccount(values: BankAccountFormPayload): Promise<BankAccountData> {
  return apiRequest<BankAccountData>("/api/v1/bank-accounts", { method: "POST", body: values });
}

export async function updateBankAccount(
  id: string,
  values: BankAccountFormPayload,
): Promise<BankAccountData> {
  return apiRequest<BankAccountData>(`/api/v1/bank-accounts/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteBankAccount(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/bank-accounts/${id}`, { method: "DELETE" });
}

export async function setDefaultBankAccount(id: string): Promise<BankAccountData> {
  return apiRequest<BankAccountData>(`/api/v1/bank-accounts/${id}/set-default`, {
    method: "POST",
  });
}

export interface AccountBalance {
  account_id: string;
  kind: AccountKind;
  balance: number;
  as_of: string;
}

export async function getBankAccountBalance(id: string): Promise<AccountBalance> {
  return apiRequest<AccountBalance>(`/api/v1/bank-accounts/${id}/balance`);
}

export type TransactionKind = "RECEITA" | "DESPESA" | "TRANSFERENCIA";

export interface TransactionData {
  id: string;
  kind: TransactionKind;
  user_id: string;
  user_name: string;
  debit_account_id: string | null;
  debit_account_name: string | null;
  credit_account_id: string | null;
  credit_account_name: string | null;
  category_id: string | null;
  category_name: string | null;
  cost_center_id: string | null;
  cost_center_name: string | null;
  customer_id: string | null;
  customer_name: string | null;
  lawsuit_id: string | null;
  description: string | null;
  amount: number;
  due_date: string;
  payment_date: string | null;
  competence: string;
  created_at: string;
  series_id: string | null;
  installment_number: number | null;
  is_internal: boolean;
  internal_note: string | null;
}

export interface ListTransactionsParams {
  kind?: TransactionKind;
  customer_id?: string;
  lawsuit_id?: string;
  status?: "paid" | "open";
  due_from?: string;
  due_to?: string;
  q?: string;
  internal?: "true" | "false" | "all";
}

export interface TransactionTotals {
  total: number;
  balance: number;
  expected: number;
}

/** Rodapé (spec 059 regra 9) somado no banco, nunca no cliente — auditoria numérica
 * da spec 060 ("nenhum cálculo de dinheiro no frontend, a UI só formata"). */
export interface TransactionListResponseData extends ListResponse<TransactionData> {
  totals: TransactionTotals;
}

export async function listTransactions(
  params: ListTransactionsParams,
): Promise<TransactionListResponseData> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const queryString = query.toString();
  return apiRequest<TransactionListResponseData>(
    `/api/v1/transactions${queryString ? `?${queryString}` : ""}`,
  );
}

export type FinancialRecurrence = "MENSAL" | "BIMESTRAL" | "TRIMESTRAL" | "SEMESTRAL" | "ANUAL";

export interface TransactionFormPayload {
  kind: TransactionKind;
  debit_account_id?: string | null;
  credit_account_id?: string | null;
  category_id?: string | null;
  cost_center_id?: string | null;
  customer_id?: string | null;
  lawsuit_id?: string | null;
  description?: string | null;
  amount: string;
  due_date: string;
  installment?: { count: number } | null;
  recurrence?: { period: FinancialRecurrence; until_date?: string | null } | null;
  is_internal?: boolean;
  internal_note?: string | null;
}

export async function createTransaction(values: TransactionFormPayload): Promise<TransactionData> {
  return apiRequest<TransactionData>("/api/v1/transactions", { method: "POST", body: values });
}

export async function updateTransaction(
  id: string,
  values: TransactionFormPayload,
): Promise<TransactionData> {
  return apiRequest<TransactionData>(`/api/v1/transactions/${id}`, {
    method: "PUT",
    body: values,
  });
}

export async function deleteTransaction(id: string): Promise<void> {
  await apiRequest<void>(`/api/v1/transactions/${id}`, { method: "DELETE" });
}

export async function payTransaction(id: string, paymentDate: string): Promise<TransactionData> {
  return apiRequest<TransactionData>(`/api/v1/transactions/${id}/pay`, {
    method: "POST",
    body: { payment_date: paymentDate },
  });
}

export async function unpayTransaction(id: string): Promise<TransactionData> {
  return apiRequest<TransactionData>(`/api/v1/transactions/${id}/unpay`, { method: "POST" });
}

export interface SeriesPreviewItem {
  id: string;
  installment_number: number | null;
  due_date: string;
  amount: number;
  payment_date: string | null;
}

export async function getSeriesPreview(transactionId: string): Promise<SeriesPreviewItem[]> {
  const body = await apiRequest<{ items: SeriesPreviewItem[] }>(
    `/api/v1/transactions/${transactionId}/series-preview`,
  );
  return body.items;
}

export interface TransactionSeriesData {
  id: string;
  is_installment: boolean;
  recurrence: FinancialRecurrence | null;
  total_installments: number | null;
  until_date: string | null;
  generated_until: string | null;
  is_active: boolean;
  created_at: string;
}

export async function getTransactionSeries(seriesId: string): Promise<TransactionSeriesData> {
  return apiRequest<TransactionSeriesData>(`/api/v1/transaction-series/${seriesId}`);
}

export type SeriesScope = "future" | "all";

export interface TransactionSeriesUpdatePayload {
  amount?: string | null;
  category_id?: string | null;
  cost_center_id?: string | null;
  description?: string | null;
}

export async function updateTransactionSeries(
  seriesId: string,
  scope: SeriesScope,
  values: TransactionSeriesUpdatePayload,
): Promise<TransactionListResponseData> {
  return apiRequest<TransactionListResponseData>(
    `/api/v1/transaction-series/${seriesId}?scope=${scope}`,
    { method: "PUT", body: values },
  );
}

export async function deleteTransactionSeries(seriesId: string, scope: SeriesScope): Promise<void> {
  await apiRequest<void>(`/api/v1/transaction-series/${seriesId}?scope=${scope}`, {
    method: "DELETE",
  });
}

export async function uploadTransactionAttachment(
  transactionId: string,
  file: File,
): Promise<AttachmentData> {
  const form = new FormData();
  form.append("file", file);
  return apiRequest<AttachmentData>(`/api/v1/transactions/${transactionId}/attachments`, {
    method: "POST",
    body: form,
  });
}

export async function listTransactionAttachments(transactionId: string): Promise<AttachmentData[]> {
  return apiRequest<AttachmentData[]>(`/api/v1/transactions/${transactionId}/attachments`);
}

export type Regime = "payment" | "due" | "competence" | "cash_flow";

export interface TransactionStats {
  balance: number;
  balance_previous: number;
  income_expected: number;
  income_realized: number;
  expense_expected: number;
  expense_realized: number;
  overdue: number;
  balance_staleness_hint: string;
}

export interface GetTransactionStatsParams {
  month?: string;
  regime?: Regime;
  account_id?: string;
}

export async function getTransactionStats(
  params: GetTransactionStatsParams,
): Promise<TransactionStats> {
  const query = new URLSearchParams();
  if (params.month) query.set("month", params.month);
  if (params.regime) query.set("regime", params.regime);
  if (params.account_id) query.set("account_id", params.account_id);
  const queryString = query.toString();
  return apiRequest<TransactionStats>(
    `/api/v1/transactions/stats${queryString ? `?${queryString}` : ""}`,
  );
}

export interface ChartPoint {
  period_start: string;
  income: number;
  expense: number;
}

export interface GetTransactionChartParams {
  month?: string;
  group_by?: "day" | "week";
  account_id?: string;
}

export async function getTransactionChart(
  params: GetTransactionChartParams,
): Promise<ChartPoint[]> {
  const query = new URLSearchParams();
  if (params.month) query.set("month", params.month);
  if (params.group_by) query.set("group_by", params.group_by);
  if (params.account_id) query.set("account_id", params.account_id);
  const queryString = query.toString();
  const body = await apiRequest<{ items: ChartPoint[] }>(
    `/api/v1/transactions/chart${queryString ? `?${queryString}` : ""}`,
  );
  return body.items;
}

export interface CashFlowPoint {
  day: string;
  income: number;
  expense: number;
  balance: number;
}

export interface GetCashFlowParams {
  from: string;
  to: string;
  account_id?: string;
}

export async function getTransactionCashFlow(params: GetCashFlowParams): Promise<CashFlowPoint[]> {
  const query = new URLSearchParams({ from: params.from, to: params.to });
  if (params.account_id) query.set("account_id", params.account_id);
  const body = await apiRequest<{ items: CashFlowPoint[] }>(
    `/api/v1/transactions/cash-flow?${query.toString()}`,
  );
  return body.items;
}

export interface AccountBalanceItem {
  account_id: string;
  name: string;
  kind: AccountKind;
  balance: number;
  is_invoice: boolean;
}

export async function listBankAccountBalances(accountId?: string): Promise<AccountBalanceItem[]> {
  const query = accountId ? `?account_id=${accountId}` : "";
  const body = await apiRequest<{ items: AccountBalanceItem[] }>(
    `/api/v1/bank-accounts/balances${query}`,
  );
  return body.items;
}

export type FinancialReportKind = "dre" | "dfc";

export interface FinancialReportGroupRow {
  dre_group_id: number;
  dre_group_name: string;
  nature: EntryType;
  receita: number;
  despesa: number;
  total: number;
}

export interface FinancialReportData {
  period_start: string;
  period_end: string;
  rows: FinancialReportGroupRow[];
  total_receita: number;
  total_despesa: number;
  resultado: number;
}

export interface GetFinancialReportParams {
  from: string;
  to: string;
  account_id?: string;
}

/** DRE (spec 062, regra 1) e DFC (regra 2) — mesmo formato de resposta, só muda a
 * rota (o backend já decide o regime de data por trás, o front não escolhe). */
export async function getFinancialReport(
  kind: FinancialReportKind,
  params: GetFinancialReportParams,
): Promise<FinancialReportData> {
  const query = new URLSearchParams({ from: params.from, to: params.to });
  if (params.account_id) query.set("account_id", params.account_id);
  return apiRequest<FinancialReportData>(`/api/v1/financial-reports/${kind}?${query.toString()}`);
}

/** Regra 8: exporta os mesmos filtros da tela — o browser decide onde salvar. */
export async function exportFinancialReport(
  report: FinancialReportKind,
  format: "xlsx" | "pdf",
  params: GetFinancialReportParams,
): Promise<void> {
  const blob = await apiRequestBlob("/api/v1/financial-reports/export", {
    method: "POST",
    body: { report, format, from: params.from, to: params.to, account_id: params.account_id },
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${report}.${format}`;
  link.click();
  URL.revokeObjectURL(url);
}

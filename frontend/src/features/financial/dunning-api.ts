import type { ListResponse } from "@/components/domain/types";
import { apiRequest } from "@/lib/api";

export type DunningChannel = "EMAIL" | "SMS" | "WHATSAPP";
export type DunningStatus = "SENT" | "FAILED" | "SKIPPED";
export type AgingBucket = "1-15" | "16-30" | "31-60" | "61-90" | "90+";

export interface OverdueTransactionData {
  id: string;
  customer_id: string | null;
  customer_name: string | null;
  lawsuit_id: string | null;
  process_number: string | null;
  description: string | null;
  amount: number;
  due_date: string;
  days_overdue: number;
}

export interface ListOverdueParams {
  aging?: AgingBucket;
  customer_id?: string;
  cursor?: string;
  limit?: number;
}

export async function listOverdue(
  params: ListOverdueParams = {},
): Promise<ListResponse<OverdueTransactionData>> {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") query.set(key, String(value));
  }
  const queryString = query.toString();
  return apiRequest<ListResponse<OverdueTransactionData>>(
    `/api/v1/transactions/overdue${queryString ? `?${queryString}` : ""}`,
  );
}

export interface AgingBucketData {
  bucket: AgingBucket;
  total: number;
}

export interface DebtorData {
  customer_id: string;
  customer_name: string;
  total: number;
}

export interface OverdueSummaryData {
  total: number;
  by_aging: AgingBucketData[];
  top_debtors: DebtorData[];
}

export async function getOverdueSummary(): Promise<OverdueSummaryData> {
  return apiRequest<OverdueSummaryData>("/api/v1/transactions/overdue/summary");
}

export interface DunningRuleData {
  id: string;
  days_offset: number;
  channel: DunningChannel;
  template: string;
  is_active: boolean;
  created_at: string;
}

export async function listDunningRules(): Promise<DunningRuleData[]> {
  const response = await apiRequest<{ items: DunningRuleData[] }>("/api/v1/dunning-rules");
  return response.items;
}

export interface DunningRuleUpsertPayload {
  days_offset: number;
  channel: DunningChannel;
  template: string;
  is_active?: boolean;
}

export async function upsertDunningRule(
  payload: DunningRuleUpsertPayload,
): Promise<DunningRuleData> {
  return apiRequest<DunningRuleData>("/api/v1/dunning-rules", { method: "PUT", body: payload });
}

export interface DunningAttemptData {
  id: string;
  transaction_id: string;
  rule_id: string | null;
  is_manual: boolean;
  channel: DunningChannel;
  sent_to: string;
  status: DunningStatus;
  error: string | null;
  sent_at: string;
}

export interface SendDunningPayload {
  channel: DunningChannel;
  template: string;
}

export async function sendDunning(
  transactionId: string,
  payload: SendDunningPayload,
): Promise<DunningAttemptData> {
  return apiRequest<DunningAttemptData>(`/api/v1/transactions/${transactionId}/dunning/send`, {
    method: "POST",
    body: payload,
  });
}

export async function listDunningAttempts(transactionId: string): Promise<DunningAttemptData[]> {
  const response = await apiRequest<{ items: DunningAttemptData[] }>(
    `/api/v1/transactions/${transactionId}/dunning/attempts`,
  );
  return response.items;
}

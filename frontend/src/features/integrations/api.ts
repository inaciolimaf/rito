import { apiRequest } from "@/lib/api";
import type { TermStatus } from "@/features/monitored-terms/api";

export interface IntegrationStatusItem {
  integration: string;
  is_healthy: boolean | null;
  last_success_at: string | null;
  avg_latency_ms: number | null;
  failures_24h: number;
}

export interface TermsByStatusItem {
  status: TermStatus;
  count: number;
}

export interface IntegrationStatus {
  integrations: IntegrationStatusItem[];
  terms_by_status: TermsByStatusItem[];
}

export interface IntegrationAlert {
  id: string;
  integration: string;
  severity: "warning" | "critical";
  code: string;
  message: string;
  responsible_user_id: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  created_at: string;
}

export interface IntegrationAlertList {
  items: IntegrationAlert[];
  total: number;
}

export interface PublicationMetrics {
  period_days: number;
  total: number;
  auto_linked: number;
  auto_link_rate: number | null;
  per_day: Record<string, number>;
  per_court: Record<string, number>;
}

export interface TermHealth {
  id: string;
  status: TermStatus;
  consecutive_failures: number;
  last_sync_at: string | null;
  last_success_at: string | null;
  next_sync_at: string | null;
  alert_id: string | null;
}

export async function getIntegrationStatus(): Promise<IntegrationStatus> {
  return apiRequest<IntegrationStatus>("/api/v1/integrations/status");
}

export async function listIntegrationAlerts(resolved?: boolean): Promise<IntegrationAlertList> {
  const query = resolved === undefined ? "" : `?resolved=${resolved}`;
  return apiRequest<IntegrationAlertList>(`/api/v1/integrations/alerts${query}`);
}

export async function resolveIntegrationAlert(id: string): Promise<IntegrationAlert> {
  return apiRequest<IntegrationAlert>(`/api/v1/integrations/alerts/${id}/resolve`, {
    method: "POST",
    body: {},
  });
}

export async function getPublicationMetrics(period = 7): Promise<PublicationMetrics> {
  return apiRequest<PublicationMetrics>(`/api/v1/publications/metrics?period=${period}`);
}

export async function getTermHealth(termId: string): Promise<TermHealth> {
  return apiRequest<TermHealth>(`/api/v1/monitored-terms/${termId}/health`);
}

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

// ---- Spec 078 — camada de agregação -------------------------------------------

export interface AggregateStatusItem {
  name: string;
  description: string;
  refresh_interval_seconds: number;
  invalidate_on: string[];
  last_refresh_at: string | null;
  last_refresh_duration_ms: number | null;
  last_error: string | null;
  is_enabled: boolean;
  computed_at: string | null;
  staleness_seconds: number | null;
  is_stale: boolean;
}

export interface AggregateStatus {
  items: AggregateStatusItem[];
}

export async function getAggregateStatus(): Promise<AggregateStatus> {
  return apiRequest<AggregateStatus>("/api/v1/aggregates/status");
}

export async function refreshAggregate(name: string): Promise<AggregateStatusItem> {
  return apiRequest<AggregateStatusItem>(`/api/v1/aggregates/${name}/refresh`, {
    method: "POST",
    body: {},
  });
}

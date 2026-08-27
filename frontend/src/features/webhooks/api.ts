import { apiRequest } from "@/lib/api";

export interface WebhookEndpointData {
  id: string;
  name: string;
  url: string;
  headers: Record<string, string>;
  is_active: boolean;
  failure_streak: number;
  disabled_at: string | null;
  created_at: string;
  /** Só vem preenchido na criação e na rotação — nunca numa listagem (regra 8). */
  secret: string | null;
}

export interface WebhookDeliveryData {
  id: string;
  endpoint_id: string;
  run_id: string | null;
  event_kind: string;
  payload: Record<string, unknown>;
  attempt: number;
  status_code: number | null;
  response_body: string | null;
  duration_ms: number | null;
  error: string | null;
  delivered_at: string | null;
  next_attempt_at: string | null;
  created_at: string;
}

export async function listEndpoints() {
  return apiRequest<{ items: WebhookEndpointData[]; total: number }>("/api/v1/webhook-endpoints");
}

export async function createEndpoint(payload: {
  name: string;
  url: string;
  headers: Record<string, string>;
}): Promise<WebhookEndpointData> {
  return apiRequest<WebhookEndpointData>("/api/v1/webhook-endpoints", {
    method: "POST",
    body: payload,
  });
}

export async function deleteEndpoint(id: string): Promise<void> {
  return apiRequest<void>(`/api/v1/webhook-endpoints/${id}`, { method: "DELETE" });
}

export async function rotateSecret(id: string): Promise<WebhookEndpointData> {
  return apiRequest<WebhookEndpointData>(`/api/v1/webhook-endpoints/${id}/rotate-secret`, {
    method: "POST",
  });
}

export async function reactivateEndpoint(id: string): Promise<WebhookEndpointData> {
  return apiRequest<WebhookEndpointData>(`/api/v1/webhook-endpoints/${id}/reactivate`, {
    method: "POST",
  });
}

export async function testEndpoint(
  id: string,
  payload: Record<string, unknown> = {},
): Promise<WebhookDeliveryData> {
  return apiRequest<WebhookDeliveryData>(`/api/v1/webhook-endpoints/${id}/test`, {
    method: "POST",
    body: { event: "task.completed", payload },
  });
}

export async function listDeliveries(endpointId?: string) {
  const query = endpointId ? `?endpoint_id=${endpointId}` : "";
  return apiRequest<{ items: WebhookDeliveryData[]; total: number }>(
    `/api/v1/webhook-deliveries${query}`,
  );
}

export async function retryDelivery(id: string): Promise<WebhookDeliveryData> {
  return apiRequest<WebhookDeliveryData>(`/api/v1/webhook-deliveries/${id}/retry`, {
    method: "POST",
  });
}

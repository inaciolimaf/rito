import { apiRequest } from "@/lib/api";

export interface IntegrationAlertData {
  id: string;
  integration: string;
  severity: "warning" | "critical";
  code: string;
  message: string;
  created_at: string;
}

export interface IntegrationAlertList {
  items: IntegrationAlertData[];
  total: number;
}

export async function listOpenIntegrationAlerts(): Promise<IntegrationAlertList> {
  return apiRequest<IntegrationAlertList>("/api/v1/integration-alerts");
}

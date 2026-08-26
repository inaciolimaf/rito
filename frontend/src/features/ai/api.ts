import { apiRequest } from "@/lib/api";

export interface ModelInfoData {
  id: string;
  name: string;
  context_length: number;
  /** Preço POR TOKEN, como o OpenRouter publica — a UI converte para 1M tokens. */
  prompt_price_usd: number;
  completion_price_usd: number;
}

export interface ModelCatalogData {
  items: ModelInfoData[];
  total: number;
  /** Falso quando não há OPENROUTER_API_KEY: a tela explica em vez de quebrar. */
  is_configured: boolean;
}

export interface FeatureConfigData {
  feature_key: string;
  label: string;
  description: string;
  model: string;
  fallback_model: string | null;
  temperature: number;
  max_tokens: number | null;
  is_enabled: boolean;
  store_prompts: boolean;
  /** Verdadeiro enquanto a feature roda com o padrão do ambiente. */
  is_default: boolean;
}

export interface FeatureConfigListData {
  items: FeatureConfigData[];
  is_configured: boolean;
  default_model: string;
}

export interface UsageGroupData {
  key: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  errors: number;
}

export interface UsageData {
  group_by: string;
  items: UsageGroupData[];
  totals: {
    calls: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost_usd: number;
    errors: number;
    avg_latency_ms: number | null;
  };
}

export async function listAiModels(): Promise<ModelCatalogData> {
  return apiRequest<ModelCatalogData>("/api/v1/ai/models");
}

export async function listFeatureConfig(): Promise<FeatureConfigListData> {
  return apiRequest<FeatureConfigListData>("/api/v1/ai/feature-config");
}

export interface FeatureConfigPayload {
  feature_key: string;
  model: string;
  fallback_model: string | null;
  temperature: number;
  max_tokens: number | null;
  is_enabled: boolean;
  store_prompts: boolean;
}

export async function saveFeatureConfig(payload: FeatureConfigPayload): Promise<FeatureConfigData> {
  return apiRequest<FeatureConfigData>("/api/v1/ai/feature-config", {
    method: "PUT",
    body: payload,
  });
}

export async function getAiUsage(groupBy: "feature" | "model" | "status"): Promise<UsageData> {
  return apiRequest<UsageData>(`/api/v1/ai/usage?group_by=${groupBy}`);
}

/** Teto mensal de gasto com IA (spec 090, alvo 2). Limite nulo é "sem teto". */
export interface SpendingAnomalyData {
  feature_key: string;
  today_usd: number;
  daily_average_usd: number;
  factor: number;
}

export interface BudgetData {
  monthly_limit_usd: number | null;
  spent_usd: number;
  used_pct: number | null;
  alert_pct: number;
  is_blocking: boolean;
  is_alerting: boolean;
  is_exceeded: boolean;
  anomalies: SpendingAnomalyData[];
}

export interface BudgetPayload {
  monthly_limit_usd: string | null;
  alert_pct: number;
  is_blocking: boolean;
}

export async function getAiBudget(): Promise<BudgetData> {
  return apiRequest<BudgetData>("/api/v1/ai/budget");
}

export async function saveAiBudget(payload: BudgetPayload): Promise<BudgetData> {
  return apiRequest<BudgetData>("/api/v1/ai/budget", { method: "PUT", body: payload });
}

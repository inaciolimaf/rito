import { apiRequest } from "@/lib/api";

export interface LegalAgentData {
  id: string;
  code: string;
  name: string;
  practice_area: string;
  system_prompt: string;
  /** Verdadeiro quando o escritório tem cópia própria deste agente. */
  is_customized: boolean;
  default_template_id: string | null;
  is_enabled: boolean;
}

export interface GenerationWarning {
  kind: string;
  text: string;
}

export interface AgentGenerationData {
  id: string;
  agent_id: string;
  lawsuit_id: string;
  thread_id: string | null;
  user_instructions: string | null;
  content: { format: string; html: string };
  template_used_id: string | null;
  model: string;
  tokens_used: number | null;
  /** Citações que a IA tentou usar sem respaldo no processo e foram removidas. */
  warnings: GenerationWarning[];
  saved_template_id: string | null;
  tool_labels: string[];
  created_at: string;
}

export async function listLegalAgents(): Promise<{ items: LegalAgentData[]; total: number }> {
  return apiRequest<{ items: LegalAgentData[]; total: number }>("/api/v1/legal-agents");
}

export async function generateBrief(
  agentId: string,
  payload: { lawsuit_id: string; instructions?: string; template_id?: string },
): Promise<AgentGenerationData> {
  return apiRequest<AgentGenerationData>(`/api/v1/legal-agents/${agentId}/generate`, {
    method: "POST",
    body: payload,
  });
}

export async function saveGenerationAsTemplate(
  generationId: string,
  name?: string,
): Promise<{ template_id: string; generation_id: string }> {
  return apiRequest<{ template_id: string; generation_id: string }>(
    `/api/v1/agent-generations/${generationId}/to-template`,
    { method: "POST", body: { name: name ?? null } },
  );
}

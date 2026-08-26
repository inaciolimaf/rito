import { apiRequest, getAccessToken } from "@/lib/api";

export type EditorTone = "formal" | "objetivo" | "tecnico" | "simples";

export interface ReviewItem {
  topic: string;
  label: string;
  status: "ok" | "atencao" | "problema" | "nao_avaliado";
  note: string;
}

export interface ReviewResult {
  action_id: string;
  items: ReviewItem[];
  /** Sempre falso: a revisão aponta, não corrige (spec 088, regra 6). */
  document_changed: boolean;
}

export interface GroundResult {
  action_id: string;
  output: string;
  warnings: { kind: string; text: string }[];
}

export async function reviewDocument(
  templateId: string,
  lawsuitId?: string,
): Promise<ReviewResult> {
  return apiRequest<ReviewResult>("/api/v1/ai/editor/review", {
    method: "POST",
    body: { template_id: templateId, lawsuit_id: lawsuitId ?? null },
  });
}

export async function suggestGrounding(
  selection: string,
  lawsuitId: string,
  templateId?: string,
): Promise<GroundResult> {
  return apiRequest<GroundResult>("/api/v1/ai/editor/ground", {
    method: "POST",
    body: { selection, lawsuit_id: lawsuitId, template_id: templateId ?? null },
  });
}

export async function sendEditorFeedback(actionId: string, accepted: boolean): Promise<void> {
  await apiRequest<void>(`/api/v1/ai/editor/actions/${actionId}/feedback`, {
    method: "POST",
    body: { accepted },
  });
}

export interface StreamHandlers {
  onChunk: (text: string) => void;
  onDone: (actionId: string | null) => void;
  onError: (message: string) => void;
}

/** Consome um endpoint SSE do editor.
 *
 * `fetch` em vez de `EventSource` porque estes endpoints são POST (o corpo carrega a
 * seleção e o contexto) e o EventSource só faz GET. */
export async function streamEditorAction(
  path: "continue" | "rewrite" | "tone",
  body: Record<string, unknown>,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const base = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
  const response = await fetch(`${base}/api/v1/ai/editor/${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getAccessToken() ?? ""}`,
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    handlers.onError("Não foi possível falar com a IA agora.");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // Eventos SSE são separados por linha em branco; o resto fica no buffer para o
    // próximo pedaço — um evento pode chegar partido.
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const event = /event:\s*(\w+)/.exec(part)?.[1];
      const data = /data:\s*(.*)/.exec(part)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data) as Record<string, string>;
      if (event === "chunk") handlers.onChunk(payload.content ?? "");
      if (event === "done") handlers.onDone(payload.action_id ?? null);
      if (event === "error") handlers.onError(payload.message ?? "Falha na geração.");
    }
  }
}

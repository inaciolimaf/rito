import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles, X } from "lucide-react";
import * as React from "react";
import { useLocation } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AIActionPreview } from "@/features/ai/AIActionPreview";
import { approveAiAction, rejectAiAction } from "@/features/ai/actions";
import { listFeatureConfig } from "@/features/ai/api";
import { ChatMessage } from "@/features/ai/ChatMessage";
import {
  deleteCopilotThread,
  getCopilotThread,
  listCopilotSuggestions,
  listCopilotThreads,
  sendCopilotMessage,
  type CopilotReply,
} from "@/features/ai/copilot";
import { StreamingMessage } from "@/features/ai/StreamingMessage";
import { SuggestionChips } from "@/features/ai/SuggestionChips";
import { ThreadHistoryList } from "@/features/ai/ThreadHistoryList";
import { ToolCallIndicator } from "@/features/ai/ToolCallIndicator";

interface Turn {
  question: string;
  reply: CopilotReply | null;
}

/** Atalho global do copiloto (spec 085 §6). */
export function useCopilotHotkey(onToggle: () => void): void {
  React.useEffect(() => {
    function handle(event: KeyboardEvent): void {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onToggle();
      }
    }
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [onToggle]);
}

/** O copiloto (spec 085): drawer lateral disponível em qualquer tela, ciente do que
 * está aberto, com as ações pendentes decididas ali mesmo.
 *
 * Sem chave de IA ou com a feature desligada, o painel simplesmente não existe
 * (regra 10) — botão que abre uma tela quebrada é pior que botão nenhum. */
export function CopilotPanel(): JSX.Element | null {
  const [open, setOpen] = React.useState(false);
  const [question, setQuestion] = React.useState("");
  const [threadId, setThreadId] = React.useState<string | null>(null);
  const [turns, setTurns] = React.useState<Turn[]>([]);
  const location = useLocation();
  const queryClient = useQueryClient();

  useCopilotHotkey(() => setOpen((value) => !value));

  const { data: config } = useQuery({
    queryKey: ["ai-feature-config"],
    queryFn: listFeatureConfig,
  });
  const { data: suggestions = [] } = useQuery({
    queryKey: ["copilot-suggestions", location.pathname],
    queryFn: () => listCopilotSuggestions(location.pathname),
    enabled: open,
  });
  const { data: history } = useQuery({
    queryKey: ["copilot-threads"],
    queryFn: listCopilotThreads,
    enabled: open,
  });
  const { data: thread } = useQuery({
    queryKey: ["copilot-thread", threadId],
    queryFn: () => getCopilotThread(threadId!),
    enabled: open && threadId !== null && turns.length === 0,
  });

  const send = useMutation({
    mutationFn: (message: string) =>
      sendCopilotMessage({
        message,
        thread_id: threadId ?? undefined,
        context: { route: location.pathname },
      }),
    onSuccess: (reply, message) => {
      setThreadId(reply.thread_id);
      setTurns((current) => [...current.slice(0, -1), { question: message, reply }]);
      void queryClient.invalidateQueries({ queryKey: ["copilot-threads"] });
    },
  });

  const decide = useMutation({
    mutationFn: ({ id, approved }: { id: string; approved: boolean }) =>
      approved ? approveAiAction(id) : rejectAiAction(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["ai-actions"] }),
  });

  const copilotFeature = config?.items.find((item) => item.feature_key === "copilot");
  const available = (config?.is_configured ?? false) && (copilotFeature?.is_enabled ?? false);
  if (!available) return null;

  function ask(message: string): void {
    if (!message.trim()) return;
    setTurns((current) => [...current, { question: message, reply: null }]);
    setQuestion("");
    send.mutate(message);
  }

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        aria-label="Abrir o copiloto (Ctrl+K)"
        onClick={() => setOpen(true)}
      >
        <Sparkles aria-hidden className="size-4" />
      </Button>

      {open && (
        <aside
          data-testid="copilot-panel"
          aria-label="Copiloto"
          className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col gap-3 border-l border-default bg-surface p-4 shadow-lg"
        >
          <header className="flex items-center justify-between">
            <h2 className="font-semibold text-primary">Copiloto</h2>
            <Button
              type="button"
              variant="ghost"
              aria-label="Fechar o copiloto"
              onClick={() => setOpen(false)}
            >
              <X aria-hidden className="size-4" />
            </Button>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto">
            {turns.length === 0 &&
              (thread?.items ?? []).map((message) => (
                <ChatMessage key={message.id} role={message.role} content={message.content} />
              ))}

            {turns.map((turn, index) => (
              <div key={`${turn.question}-${index}`} className="space-y-2">
                <ChatMessage role="user" content={turn.question} />
                {turn.reply === null ? (
                  <StreamingMessage chunks={[]} isStreaming />
                ) : (
                  <>
                    <ToolCallIndicator labels={turn.reply.tool_labels} isRunning={false} />
                    <ChatMessage role="assistant" content={turn.reply.reply} />
                    {turn.reply.pending_action && (
                      <AIActionPreview
                        preview={turn.reply.pending_action.preview}
                        isDeciding={decide.isPending}
                        onApprove={() =>
                          decide.mutateAsync({
                            id: turn.reply!.pending_action!.action_id,
                            approved: true,
                          })
                        }
                        onReject={() =>
                          decide.mutateAsync({
                            id: turn.reply!.pending_action!.action_id,
                            approved: false,
                          })
                        }
                      />
                    )}
                  </>
                )}
              </div>
            ))}
          </div>

          <SuggestionChips suggestions={suggestions} onPick={ask} disabled={send.isPending} />

          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              ask(question);
            }}
          >
            <Input
              aria-label="Pergunte ao copiloto"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="Pergunte sobre processos, prazos, financeiro…"
            />
            <Button type="submit" disabled={send.isPending || !question.trim()}>
              Enviar
            </Button>
          </form>

          <details className="text-xs text-muted">
            <summary className="cursor-pointer">Conversas anteriores</summary>
            <div className="mt-2">
              <ThreadHistoryList
                threads={history?.items ?? []}
                activeId={threadId}
                onOpen={(id) => {
                  setThreadId(id);
                  setTurns([]);
                }}
                onDelete={(id) => {
                  void deleteCopilotThread(id).then(() =>
                    queryClient.invalidateQueries({ queryKey: ["copilot-threads"] }),
                  );
                  if (id === threadId) setThreadId(null);
                }}
              />
            </div>
          </details>
        </aside>
      )}
    </>
  );
}

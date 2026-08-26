import { Trash2 } from "lucide-react";

import { EmptyState } from "@/components/domain/EmptyState";
import type { CopilotThreadSummary } from "@/features/ai/copilot";

export interface ThreadHistoryListProps {
  threads: CopilotThreadSummary[];
  activeId: string | null;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}

/** Conversas anteriores do usuário (spec 085, regra 6). Arquivada continua na lista,
 * marcada — sumir seria perder o histórico sem avisar. */
export function ThreadHistoryList({
  threads,
  activeId,
  onOpen,
  onDelete,
}: ThreadHistoryListProps): JSX.Element {
  if (threads.length === 0) {
    return <EmptyState title="Nenhuma conversa ainda" />;
  }
  return (
    <ul className="space-y-1" data-testid="thread-history">
      {threads.map((thread) => (
        <li key={thread.id} className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onOpen(thread.id)}
            aria-current={thread.id === activeId}
            className={
              thread.id === activeId
                ? "flex-1 truncate rounded border border-accent px-2 py-1 text-left text-xs text-primary"
                : "flex-1 truncate rounded border border-default px-2 py-1 text-left text-xs text-muted hover:text-primary"
            }
          >
            {thread.title ?? "Conversa sem título"}
            {thread.archived_at && <span className="ml-1 text-muted">(arquivada)</span>}
          </button>
          <button
            type="button"
            aria-label={`Excluir conversa ${thread.title ?? ""}`}
            onClick={() => onDelete(thread.id)}
            className="rounded p-1 text-muted hover:text-danger"
          >
            <Trash2 aria-hidden className="size-3" />
          </button>
        </li>
      ))}
    </ul>
  );
}

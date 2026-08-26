import * as React from "react";

export interface ChatMessageProps {
  role: "user" | "assistant" | "tool" | "system";
  /** Nulo quando o escritório não pediu para guardar o conteúdo (spec 085, regra 13). */
  content: string | null;
  children?: React.ReactNode;
}

/** Uma fala da conversa. Mensagem sem conteúdo não some do histórico: ela vira a marca
 * de que houve uma troca cujo texto o escritório optou por não guardar. */
export function ChatMessage({ role, content, children }: ChatMessageProps): JSX.Element {
  const isUser = role === "user";
  return (
    <div
      data-testid={`chat-message-${role}`}
      className={isUser ? "flex justify-end" : "flex justify-start"}
    >
      <div
        className={
          isUser
            ? "max-w-[85%] rounded-lg bg-accent/15 px-3 py-2 text-sm text-primary"
            : "max-w-[85%] space-y-2 rounded-lg bg-surface-muted px-3 py-2 text-sm text-primary"
        }
      >
        {content ? (
          <p className="whitespace-pre-wrap">{content}</p>
        ) : (
          <p className="italic text-muted">
            Conteúdo não guardado — este escritório não ativou o histórico de conversas.
          </p>
        )}
        {children}
      </div>
    </div>
  );
}

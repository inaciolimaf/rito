import * as React from "react";

export interface SlashCommand {
  id: "continue" | "rewrite" | "tone" | "review" | "ground";
  label: string;
  description: string;
}

export const AI_COMMANDS: SlashCommand[] = [
  {
    id: "continue",
    label: "Continuar escrevendo",
    description: "A IA segue o texto de onde o cursor está.",
  },
  {
    id: "rewrite",
    label: "Reescrever seleção",
    description: "Reescreve só o trecho selecionado, com a sua instrução.",
  },
  { id: "tone", label: "Ajustar o tom", description: "Formal, objetivo, técnico ou simples." },
  {
    id: "review",
    label: "Revisar a peça",
    description: "Checklist de estrutura, fundamentação, pedidos, datas e linguagem.",
  },
  {
    id: "ground",
    label: "Sugerir fundamentação",
    description: "Usa o contexto do processo. Não inventa citação.",
  },
];

export interface SlashCommandMenuProps {
  open: boolean;
  /** Regra 11: sem IA configurada, o menu não mostra comando de IA nenhum. */
  aiAvailable: boolean;
  onPick: (command: SlashCommand) => void;
  onClose: () => void;
}

/** Menu de comandos do editor, aberto com `/` (spec 088 §6). */
export function SlashCommandMenu({
  open,
  aiAvailable,
  onPick,
  onClose,
}: SlashCommandMenuProps): JSX.Element | null {
  React.useEffect(() => {
    function handle(event: KeyboardEvent): void {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handle);
    return () => window.removeEventListener("keydown", handle);
  }, [onClose]);

  if (!open) return null;
  if (!aiAvailable) {
    return (
      <div
        data-testid="slash-menu"
        className="rounded border border-default bg-surface p-3 text-sm text-muted"
      >
        Nenhum comando de IA disponível — o escritório não tem IA configurada.
      </div>
    );
  }
  return (
    <ul
      data-testid="slash-menu"
      aria-label="Comandos de IA"
      className="max-h-64 overflow-y-auto rounded border border-default bg-surface p-1 text-sm"
    >
      {AI_COMMANDS.map((command) => (
        <li key={command.id}>
          <button
            type="button"
            onClick={() => onPick(command)}
            className="w-full rounded px-2 py-1 text-left hover:bg-surface-muted"
          >
            <span className="block text-primary">{command.label}</span>
            <span className="block text-xs text-muted">{command.description}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

import * as React from "react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { LegalAgentData } from "@/features/legal-agents/api";

export interface AgentPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  agents: LegalAgentData[];
  onPick: (agent: LegalAgentData) => void;
}

/** Grade de agentes por área (spec 087 §6). Dezenove opções não cabem num select —
 * o filtro por área é o que faz a escolha ser rápida. */
export function AgentPickerDialog({
  open,
  onOpenChange,
  agents,
  onPick,
}: AgentPickerDialogProps): JSX.Element {
  const [query, setQuery] = React.useState("");
  const filtrados = agents.filter((agent) =>
    `${agent.name} ${agent.practice_area}`.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Escolher o agente</DialogTitle>
        <DialogDescription>
          Cada agente escreve na linguagem e na estrutura da própria área.
        </DialogDescription>

        <Input
          aria-label="Buscar agente por área"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Trabalhista, consumidor, família…"
          className="mt-3"
        />

        <ul className="mt-3 grid max-h-80 gap-2 overflow-y-auto sm:grid-cols-2">
          {filtrados.map((agent) => (
            <li key={agent.id}>
              <button
                type="button"
                onClick={() => onPick(agent)}
                className="w-full rounded border border-default p-2 text-left text-sm hover:border-accent"
              >
                <span className="block font-medium text-primary">{agent.practice_area}</span>
                <span className="block text-xs text-muted">
                  {agent.name}
                  {agent.is_customized ? " · personalizado" : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  );
}

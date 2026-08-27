import * as React from "react";

import { BranchEditor } from "@/features/automations/BranchEditor";

/** Ferramentas de LEITURA que a decisão pode usar para buscar contexto (spec 083).
 * A lista é curta de propósito: oferecer as 16 para responder "é urgente?" é pagar por
 * catálogo que o modelo não vai usar. */
const CONTEXT_TOOLS = [
  { value: "get_lawsuit", label: "Dados do processo" },
  { value: "get_lawsuit_timeline", label: "Andamentos do processo" },
  { value: "get_publication", label: "Texto da intimação" },
  { value: "get_customer", label: "Dados do cliente" },
  { value: "search_tasks", label: "Tarefas do período" },
];

export interface DecisionConfig {
  question: string;
  branches: string[];
  default_branch: string;
  min_confidence: number;
  context_tools: string[];
}

export interface LlmDecisionActionProps {
  config: DecisionConfig;
  assignment: Record<string, number[]>;
  candidates: { position: number; label: string }[];
  onChange: (config: DecisionConfig, assignment: Record<string, number[]>) => void;
}

/** Configuração do nó de decisão (spec 094 §7).
 *
 * O ramo padrão não é um detalhe do formulário: é o caminho que a automação segue quando
 * a IA falhar, e sem ele a regra 5 não teria como ser cumprida. Por isso ele é um campo
 * obrigatório e explicado, não uma opção escondida. */
export function LlmDecisionAction({
  config,
  assignment,
  candidates,
  onChange,
}: LlmDecisionActionProps): JSX.Element {
  const [novoRamo, setNovoRamo] = React.useState("");

  function atualizar(patch: Partial<DecisionConfig>): void {
    onChange({ ...config, ...patch }, assignment);
  }

  return (
    <div className="space-y-3" aria-label="Decisão por IA">
      <label className="flex flex-col text-xs text-muted">
        Pergunta
        <input
          aria-label="Pergunta da decisão"
          className="mt-1 rounded border border-default bg-surface p-1 text-sm"
          placeholder="Ex.: esta intimação exige resposta em até 5 dias?"
          value={config.question}
          onChange={(event) => atualizar({ question: event.target.value })}
        />
      </label>

      <div className="space-y-1">
        <span className="text-xs text-muted">Ramos</span>
        <div className="flex flex-wrap items-center gap-2">
          {config.branches.map((branch) => (
            <span
              key={branch}
              className="flex items-center gap-1 rounded bg-muted/20 px-2 py-0.5 text-xs"
            >
              {branch}
              <button
                type="button"
                aria-label={`Remover ramo ${branch}`}
                onClick={() =>
                  atualizar({
                    branches: config.branches.filter((item) => item !== branch),
                    default_branch: config.default_branch === branch ? "" : config.default_branch,
                  })
                }
              >
                ×
              </button>
            </span>
          ))}
          <input
            aria-label="Novo ramo"
            className="w-32 rounded border border-default bg-surface p-1 text-xs"
            placeholder="novo ramo"
            value={novoRamo}
            onChange={(event) => setNovoRamo(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && novoRamo.trim()) {
                event.preventDefault();
                atualizar({ branches: [...config.branches, novoRamo.trim()] });
                setNovoRamo("");
              }
            }}
          />
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-xs text-muted">
          Ramo padrão
          <select
            aria-label="Ramo padrão"
            className="mt-1 rounded border border-default bg-surface p-1 text-sm"
            value={config.default_branch}
            onChange={(event) => atualizar({ default_branch: event.target.value })}
          >
            <option value="">Escolha…</option>
            {config.branches.map((branch) => (
              <option key={branch} value={branch}>
                {branch}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs text-muted">
          Confiança mínima
          <input
            aria-label="Confiança mínima"
            type="number"
            min={0}
            max={1}
            step={0.05}
            className="mt-1 w-24 rounded border border-default bg-surface p-1 text-sm"
            value={config.min_confidence}
            onChange={(event) => atualizar({ min_confidence: Number(event.target.value) })}
          />
        </label>
      </div>
      <p className="text-[11px] text-muted">
        Se a IA falhar, responder algo fora da lista ou ficar abaixo da confiança mínima, a
        automação segue pelo ramo padrão — ela nunca para por causa da IA.
      </p>

      <div className="space-y-1">
        <span className="text-xs text-muted">Contexto que a IA pode consultar</span>
        <div className="flex flex-wrap gap-3">
          {CONTEXT_TOOLS.map((tool) => (
            <label key={tool.value} className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                aria-label={tool.label}
                checked={config.context_tools.includes(tool.value)}
                onChange={(event) =>
                  atualizar({
                    context_tools: event.target.checked
                      ? [...config.context_tools, tool.value]
                      : config.context_tools.filter((item) => item !== tool.value),
                  })
                }
              />
              {tool.label}
            </label>
          ))}
        </div>
        <p className="text-[11px] text-muted">
          Só leitura: o nó de decisão nunca altera nada no sistema.
        </p>
      </div>

      <BranchEditor
        branches={config.branches}
        assignment={assignment}
        candidates={candidates}
        onChange={(proximo) => onChange(config, proximo)}
      />
    </div>
  );
}

import * as React from "react";

import { ActionRow, type ActionDraft } from "@/features/automations/ActionRow";
import { TriggerSelect } from "@/features/automations/TriggerSelect";
import type { AutomationData, AutomationPayload, TriggerKind } from "@/features/automations/api";
import { ACTION_LABELS } from "@/features/automations/labels";

/** Regra 13 do backend, repetida aqui para o usuário não descobrir no 422. */
const MAX_ACTIONS = 20;

function novaAcao(): ActionDraft {
  return {
    action_kind: "create_task",
    action_config: {},
    delay_kind: "immediate",
    delay_value: null,
    condition: null,
  };
}

export interface AutomationBuilderProps {
  automation?: AutomationData;
  onSave: (payload: AutomationPayload) => void;
  isSaving?: boolean;
  error?: string | null;
}

/** Editor de automação (spec 092 §6): gatilho no topo, ações em sequência.
 *
 * A tela é uma frase: "quando ISTO acontecer, faça AQUILO, e depois AQUILO". Por isso o
 * gatilho não é um campo no meio de um formulário — ele é o cabeçalho, e as ações se
 * leem de cima para baixo na ordem em que rodam. */
export function AutomationBuilder({
  automation,
  onSave,
  isSaving = false,
  error = null,
}: AutomationBuilderProps): JSX.Element {
  const [nome, setNome] = React.useState(automation?.name ?? "");
  const [gatilho, setGatilho] = React.useState<TriggerKind>(
    automation?.trigger_kind ?? "lawsuit.created",
  );
  const [acoes, setAcoes] = React.useState<ActionDraft[]>(
    automation?.actions.map((item) => ({
      action_kind: item.action_kind,
      action_config: item.action_config,
      delay_kind: item.delay_kind,
      delay_value: item.delay_value,
      condition: item.condition,
      branches: item.branches,
    })) ?? [novaAcao()],
  );

  const cheia = acoes.length >= MAX_ACTIONS;

  return (
    <form
      className="space-y-4"
      aria-label="Editor de automação"
      onSubmit={(event) => {
        event.preventDefault();
        onSave({
          name: nome,
          trigger_kind: gatilho,
          trigger_config: automation?.trigger_config ?? {},
          actions: acoes,
        });
      }}
    >
      <label className="flex flex-col text-xs text-muted">
        Nome da automação
        <input
          aria-label="Nome da automação"
          className="mt-1 rounded border border-default bg-surface p-2 text-sm"
          value={nome}
          onChange={(event) => setNome(event.target.value)}
          placeholder="Ex.: Processo trabalhista novo abre cálculo"
        />
      </label>

      <TriggerSelect value={gatilho} onChange={setGatilho} />

      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-primary">Então, na ordem:</h3>
        <ol className="space-y-2">
          {acoes.map((acao, indice) => (
            <ActionRow
              key={indice}
              index={indice}
              action={acao}
              // Só o que vem DEPOIS pode compor um ramo: uma ação anterior à decisão
              // já rodou quando ela acontece.
              candidates={acoes
                .map((item, posicao) => ({
                  position: posicao,
                  label: `${posicao + 1}. ${ACTION_LABELS[item.action_kind]}`,
                }))
                .filter((item) => item.position > indice)}
              onChange={(atualizada) =>
                setAcoes((atual) =>
                  atual.map((item, posicao) => (posicao === indice ? atualizada : item)),
                )
              }
              onRemove={() =>
                setAcoes((atual) => atual.filter((_item, posicao) => posicao !== indice))
              }
            />
          ))}
        </ol>
        <button
          type="button"
          className="rounded border border-default px-3 py-1 text-sm"
          disabled={cheia}
          onClick={() => setAcoes((atual) => [...atual, novaAcao()])}
        >
          Adicionar ação
        </button>
        {cheia && (
          <p className="text-xs text-warning">
            Uma automação aceita no máximo {MAX_ACTIONS} ações. Acima disso, divida em duas.
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="rounded border border-danger bg-danger/10 p-2 text-sm">
          {error}
        </p>
      )}

      <button
        type="submit"
        className="rounded bg-primary px-3 py-1 text-sm text-on-primary"
        disabled={isSaving || nome.trim().length < 2}
      >
        Salvar automação
      </button>
    </form>
  );
}

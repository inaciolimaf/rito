import type { ActionKind, DelayKind } from "@/features/automations/api";
import { ACTION_LABELS, DELAY_LABELS } from "@/features/automations/labels";

export interface ActionDraft {
  action_kind: ActionKind;
  action_config: Record<string, unknown>;
  delay_kind: DelayKind;
  delay_value: number | null;
  condition: Record<string, unknown> | null;
}

export interface ActionRowProps {
  index: number;
  action: ActionDraft;
  onChange: (action: ActionDraft) => void;
  onRemove: () => void;
}

/** Um passo da sequência: o que fazer, quando, e sob qual condição.
 *
 * A ordem visual é a ordem de execução — `position` é o índice na lista, e não um campo
 * que a pessoa preenche. Número de posição digitado à mão é convite para dois passos
 * "3" e uma automação que roda fora de ordem. */
export function ActionRow({ index, action, onChange, onRemove }: ActionRowProps): JSX.Element {
  const precisaDeDias =
    action.delay_kind === "business_days" || action.delay_kind === "calendar_days";

  return (
    <li className="space-y-2 rounded border border-default p-3" aria-label={`Ação ${index + 1}`}>
      <div className="flex items-center gap-2">
        <span className="rounded bg-muted/20 px-2 py-0.5 text-xs text-muted">{index + 1}</span>
        <select
          aria-label={`Tipo da ação ${index + 1}`}
          className="flex-1 rounded border border-default bg-surface p-1 text-sm"
          value={action.action_kind}
          onChange={(event) =>
            onChange({ ...action, action_kind: event.target.value as ActionKind })
          }
        >
          {Object.entries(ACTION_LABELS).map(([kind, label]) => (
            <option key={kind} value={kind}>
              {label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="rounded border border-default px-2 py-1 text-xs"
          onClick={onRemove}
          aria-label={`Remover ação ${index + 1}`}
        >
          Remover
        </button>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col text-xs text-muted">
          Quando
          <select
            aria-label={`Tempo da ação ${index + 1}`}
            className="mt-1 rounded border border-default bg-surface p-1 text-sm"
            value={action.delay_kind}
            onChange={(event) =>
              onChange({
                ...action,
                delay_kind: event.target.value as DelayKind,
                delay_value: event.target.value.endsWith("_days")
                  ? (action.delay_value ?? 1)
                  : null,
              })
            }
          >
            {Object.entries(DELAY_LABELS).map(([kind, label]) => (
              <option key={kind} value={kind}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {precisaDeDias && (
          <label className="flex flex-col text-xs text-muted">
            Dias
            <input
              aria-label={`Dias da ação ${index + 1}`}
              type="number"
              min={0}
              max={365}
              className="mt-1 w-20 rounded border border-default bg-surface p-1 text-sm"
              value={action.delay_value ?? 0}
              onChange={(event) => onChange({ ...action, delay_value: Number(event.target.value) })}
            />
          </label>
        )}
      </div>
    </li>
  );
}

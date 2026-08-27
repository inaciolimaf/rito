import type { TriggerKind } from "@/features/automations/api";
import { TRIGGER_LABELS } from "@/features/automations/labels";

export interface TriggerSelectProps {
  value: TriggerKind;
  onChange: (value: TriggerKind) => void;
}

/** O gatilho fica no topo do builder porque é o que dá sentido ao resto: sem saber
 * QUANDO, nenhuma das ações abaixo significa coisa alguma. */
export function TriggerSelect({ value, onChange }: TriggerSelectProps): JSX.Element {
  return (
    <label className="flex flex-col text-xs text-muted">
      Gatilho
      <select
        aria-label="Gatilho"
        className="mt-1 rounded border border-default bg-surface p-2 text-sm"
        value={value}
        onChange={(event) => onChange(event.target.value as TriggerKind)}
      >
        {Object.entries(TRIGGER_LABELS).map(([kind, label]) => (
          <option key={kind} value={kind}>
            {label}
          </option>
        ))}
      </select>
    </label>
  );
}

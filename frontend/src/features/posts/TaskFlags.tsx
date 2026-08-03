export interface TaskFlagsValue {
  is_important: boolean;
  is_urgent: boolean;
  is_future: boolean;
  is_private: boolean;
  show_in_schedule: boolean;
}

export interface TaskFlagsProps {
  value: TaskFlagsValue;
  onChange: (value: TaskFlagsValue) => void;
}

const FLAG_ITEMS = [
  { key: "is_important", label: "Importante" },
  { key: "is_urgent", label: "Urgente" },
  { key: "is_future", label: "Futura (oculta até a data)" },
  { key: "is_private", label: "Privada" },
  { key: "show_in_schedule", label: "Mostrar na agenda" },
] as const;

/** Flags da tarefa (spec 033): important/urgent são independentes e combináveis
 * (regra 10); futura oculta até a data (regra 7); privada restringe a visibilidade
 * (regra 8). */
export function TaskFlags({ value, onChange }: TaskFlagsProps): JSX.Element {
  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-medium text-primary">Flags</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {FLAG_ITEMS.map((item) => (
          <label
            key={item.key}
            className="flex items-center gap-2 text-sm text-primary"
            htmlFor={`flag-${item.key}`}
          >
            <input
              id={`flag-${item.key}`}
              type="checkbox"
              checked={value[item.key]}
              onChange={(event) => onChange({ ...value, [item.key]: event.target.checked })}
            />
            {item.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

import { useQuery } from "@tanstack/react-query";

import { listTemplateVariables } from "@/features/templates/api";

const NAMESPACE_LABELS: Record<string, string> = {
  cliente: "Cliente",
  processo: "Processo",
  escritorio: "Escritório",
  usuario: "Usuário",
};

export interface VariablePickerProps {
  onInsert: (token: string) => void;
}

/** Seletor "Inserir variável" (spec 066) — insere `{{namespace.campo}}` na posição
 * do cursor do `TemplateEditor`; a resolução de verdade (spec 067) acontece na hora
 * de gerar o documento, não aqui. */
export function VariablePicker({ onInsert }: VariablePickerProps): JSX.Element {
  const { data } = useQuery({
    queryKey: ["template-variables"],
    queryFn: listTemplateVariables,
  });

  const grouped = new Map<string, { key: string; label: string }[]>();
  for (const item of data ?? []) {
    const list = grouped.get(item.namespace) ?? [];
    list.push({ key: item.key, label: item.label });
    grouped.set(item.namespace, list);
  }

  return (
    <select
      aria-label="Inserir variável"
      className="h-8 rounded border border-default bg-surface px-1 text-sm text-primary"
      value=""
      onChange={(event) => {
        if (event.target.value) onInsert(`{{${event.target.value}}}`);
      }}
    >
      <option value="">Inserir variável</option>
      {Array.from(grouped.entries()).map(([namespace, fields]) => (
        <optgroup key={namespace} label={NAMESPACE_LABELS[namespace] ?? namespace}>
          {fields.map((field) => (
            <option key={field.key} value={`${namespace}.${field.key}`}>
              {field.label}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  );
}

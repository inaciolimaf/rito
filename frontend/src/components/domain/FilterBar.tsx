import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";

export interface FilterBarProps {
  fields: FilterFieldDef[];
}

/** Regra 2: filtros vivem na URL via `useFilters` — recarregar preserva o estado. */
export function FilterBar({ fields }: FilterBarProps): JSX.Element {
  const { values, setValue, clear, activeCount } = useFilters(fields);

  return (
    <div className="flex flex-wrap items-end gap-3 rounded border border-default bg-surface p-3">
      {fields.map((field) => (
        <div key={field.key} className="flex flex-col gap-1">
          <Label htmlFor={`filter-${field.key}`}>{field.label}</Label>
          {renderField(field, values[field.key], (value) => setValue(field.key, value))}
        </div>
      ))}

      <Button type="button" variant="ghost" size="sm" onClick={clear} disabled={activeCount === 0}>
        <X className="mr-1 h-4 w-4" />
        Limpar filtros{activeCount > 0 && ` (${activeCount})`}
      </Button>
    </div>
  );
}

function renderField(
  field: FilterFieldDef,
  value: string | string[] | undefined,
  onChange: (value: string | string[] | undefined) => void,
): JSX.Element {
  const id = `filter-${field.key}`;

  if (field.type === "select") {
    return (
      <select
        id={id}
        className="h-10 rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || undefined)}
      >
        <option value="">Todos</option>
        {field.options?.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (field.type === "multiselect") {
    const selected = Array.isArray(value) ? value : [];
    return (
      <select
        id={id}
        multiple
        className="h-20 rounded border border-default bg-surface px-3 py-1 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        value={selected}
        onChange={(event) => {
          const next = Array.from(event.target.selectedOptions).map((option) => option.value);
          onChange(next.length > 0 ? next : undefined);
        }}
      >
        {field.options?.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (field.type === "boolean") {
    return (
      <select
        id={id}
        className="h-10 rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || undefined)}
      >
        <option value="">Todos</option>
        <option value="true">Sim</option>
        <option value="false">Não</option>
      </select>
    );
  }

  if (field.type === "date") {
    return (
      <Input
        id={id}
        type="date"
        value={typeof value === "string" ? value : ""}
        onChange={(event) => onChange(event.target.value || undefined)}
      />
    );
  }

  return (
    <Input
      id={id}
      type="text"
      value={typeof value === "string" ? value : ""}
      onChange={(event) => onChange(event.target.value || undefined)}
    />
  );
}

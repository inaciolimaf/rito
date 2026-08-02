import * as React from "react";

import { Input } from "@/components/ui/input";
import { getLawsuitFolders, type FolderSuggestion } from "@/features/lawsuits/api";

export interface FolderAutocompleteProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
  maxLength?: number;
  placeholder?: string;
}

const DEBOUNCE_MS = 200;

/** Autocomplete de pasta (spec 029): sugere as pastas já usadas no tenant por
 * frequência (regra 7), mas aceita valor novo — não é lista fechada (regra 1). */
export function FolderAutocomplete({
  id,
  value,
  onChange,
  maxLength = 30,
  placeholder,
}: FolderAutocompleteProps): JSX.Element {
  const [open, setOpen] = React.useState(false);
  const [suggestions, setSuggestions] = React.useState<FolderSuggestion[]>([]);
  const [debounced, setDebounced] = React.useState(value);

  React.useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value]);

  React.useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void getLawsuitFolders(debounced || undefined).then((result) => {
      if (!cancelled) setSuggestions(result);
    });
    return () => {
      cancelled = true;
    };
  }, [debounced, open]);

  return (
    <div className="relative">
      <Input
        id={id}
        value={value}
        maxLength={maxLength}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls={id ? `${id}-suggestions` : undefined}
        onChange={(event) => {
          // Regra 1: digitar um nome inexistente é válido — o valor sobe do mesmo jeito.
          onChange(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          // Delay para o click da sugestão registrar antes do dropdown fechar.
          setTimeout(() => setOpen(false), 150);
        }}
      />
      {open && suggestions.length > 0 && (
        <ul
          id={id ? `${id}-suggestions` : undefined}
          role="listbox"
          className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded border border-default bg-surface shadow-md"
        >
          {suggestions.map((suggestion) => (
            <li key={suggestion.name}>
              <button
                type="button"
                role="option"
                aria-selected={suggestion.name === value}
                className="flex w-full items-center justify-between px-3 py-1.5 text-left text-sm hover:bg-surface-muted"
                onMouseDown={(event) => {
                  event.preventDefault();
                  onChange(suggestion.name);
                  setOpen(false);
                }}
              >
                <span className="text-primary">{suggestion.name}</span>
                <span className="text-muted">{suggestion.count}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

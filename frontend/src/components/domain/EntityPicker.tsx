import { X } from "lucide-react";
import * as React from "react";

import { Input } from "@/components/ui/input";
import type { EntityOption } from "@/components/domain/types";
import { cn } from "@/lib/utils";

export interface EntityPickerProps {
  value: EntityOption[];
  onChange: (value: EntityOption[]) => void;
  onSearch: (query: string) => Promise<EntityOption[]>;
  multiple?: boolean;
  placeholder?: string;
  label?: string;
  debounceMs?: number;
}

/** Busca assíncrona debounced (regra: seleção simples ou múltipla). */
export function EntityPicker({
  value,
  onChange,
  onSearch,
  multiple = false,
  placeholder = "Buscar...",
  label = "Buscar",
  debounceMs = 300,
}: EntityPickerProps): JSX.Element {
  const [query, setQuery] = React.useState("");
  const [options, setOptions] = React.useState<EntityOption[]>([]);
  const [isOpen, setIsOpen] = React.useState(false);
  const [activeIndex, setActiveIndex] = React.useState(-1);
  const containerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (query.trim() === "") {
      setOptions([]);
      return;
    }
    const timeout = setTimeout(() => {
      void onSearch(query).then((results) => {
        setOptions(results);
        setActiveIndex(-1);
      });
    }, debounceMs);
    return () => clearTimeout(timeout);
  }, [query, onSearch, debounceMs]);

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function selectOption(option: EntityOption): void {
    if (multiple) {
      if (!value.some((item) => item.id === option.id)) {
        onChange([...value, option]);
      }
    } else {
      onChange([option]);
    }
    setQuery("");
    setOptions([]);
    setIsOpen(false);
  }

  function removeOption(id: string): void {
    onChange(value.filter((item) => item.id !== id));
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>): void {
    if (!isOpen || options.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, options.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      const option = options[activeIndex];
      if (option) {
        selectOption(option);
      }
    } else if (event.key === "Escape") {
      setIsOpen(false);
    }
  }

  const listboxId = React.useId();

  return (
    <div ref={containerRef} className="relative flex flex-col gap-1">
      {value.length > 0 && (
        <ul className="flex flex-wrap gap-1" aria-label="Selecionados">
          {value.map((item) => (
            <li
              key={item.id}
              className="flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-sm text-primary"
            >
              {item.label}
              <button
                type="button"
                onClick={() => removeOption(item.id)}
                aria-label={`Remover ${item.label}`}
                className="text-muted hover:text-danger"
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <Input
        aria-label={label}
        placeholder={placeholder}
        value={query}
        role="combobox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        aria-autocomplete="list"
        onFocus={() => setIsOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setIsOpen(true);
        }}
        onKeyDown={handleKeyDown}
      />

      {isOpen && options.length > 0 && (
        <ul
          id={listboxId}
          role="listbox"
          className="absolute top-full z-10 mt-1 max-h-56 w-full overflow-auto rounded border border-default bg-surface shadow-lg"
        >
          {options.map((option, index) => (
            <li
              key={option.id}
              role="option"
              aria-selected={index === activeIndex}
              className={cn(
                "cursor-pointer px-3 py-2 text-sm text-primary hover:bg-surface-muted",
                index === activeIndex && "bg-surface-muted",
              )}
              onMouseDown={(event) => {
                event.preventDefault();
                selectOption(option);
              }}
            >
              {option.label}
              {option.description && (
                <span className="block text-xs text-muted">{option.description}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

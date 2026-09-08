import { X } from "lucide-react";
import * as React from "react";

import { useClickOutside } from "@/components/domain/useClickOutside";
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

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "done"; options: EntityOption[] }
  | { status: "error" };

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
  const [search, setSearch] = React.useState<SearchState>({ status: "idle" });
  const [activeIndex, setActiveIndex] = React.useState(-1);
  const [isOpen, setIsOpen] = React.useState(false);
  const closePicker = React.useCallback(() => setIsOpen(false), []);
  const containerRef = useClickOutside<HTMLDivElement>(isOpen, closePicker);
  const options = search.status === "done" ? search.options : [];

  // Spec 138, regra 6: o cleanup do efeito cancela o *timer*, nunca a requisição já
  // disparada. Sem um número de sequência, digitar rápido faz a resposta lenta de um
  // prefixo antigo chegar depois da resposta certa e substituí-la — a lista pisca com o
  // resultado bom e volta para o velho, e quem clica seleciona o registro errado.
  // `requestId` é o relógio dessa corrida: só a resposta da busca mais recente escreve.
  const requestId = React.useRef(0);

  React.useEffect(() => {
    if (query.trim() === "") {
      requestId.current += 1;
      setSearch({ status: "idle" });
      return;
    }
    const timeout = setTimeout(() => {
      requestId.current += 1;
      const current = requestId.current;
      setSearch({ status: "loading" });
      onSearch(query).then(
        (results) => {
          if (current !== requestId.current) return;
          setSearch({ status: "done", options: results });
          setActiveIndex(-1);
        },
        () => {
          // Sem este ramo, uma busca que falha virava unhandled rejection e a lista
          // simplesmente não abria — "nada acontece" não é estado (spec 007, regra 7).
          if (current !== requestId.current) return;
          setSearch({ status: "error" });
          setActiveIndex(-1);
        },
      );
    }, debounceMs);
    return () => clearTimeout(timeout);
  }, [query, onSearch, debounceMs]);

  function selectOption(option: EntityOption): void {
    if (multiple) {
      if (!value.some((item) => item.id === option.id)) {
        onChange([...value, option]);
      }
    } else {
      onChange([option]);
    }
    requestId.current += 1;
    setQuery("");
    setSearch({ status: "idle" });
    setIsOpen(false);
  }

  function removeOption(id: string): void {
    onChange(value.filter((item) => item.id !== id));
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>): void {
    if (event.key === "Escape") {
      setIsOpen(false);
      return;
    }
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
    }
  }

  const listboxId = React.useId();
  const optionId = (index: number): string => `${listboxId}-option-${index}`;
  const activeOptionId = activeIndex >= 0 ? optionId(activeIndex) : undefined;
  // A lista abre também para dizer "buscando", "nada encontrado" e "a busca falhou" — a
  // seção 9 da spec 007 promete um combobox completo, e um combobox que só aparece
  // quando dá certo esconde metade do que aconteceu.
  const showPanel = isOpen && search.status !== "idle";

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
        aria-activedescendant={activeOptionId}
        onFocus={() => setIsOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          setIsOpen(true);
        }}
        onKeyDown={handleKeyDown}
      />

      {showPanel && (
        <div className="absolute top-full z-10 mt-1 w-full rounded border border-default bg-surface shadow-lg">
          {search.status === "loading" && (
            <p role="status" className="px-3 py-2 text-sm text-muted">
              Buscando…
            </p>
          )}
          {search.status === "error" && (
            <p role="alert" className="px-3 py-2 text-sm text-danger">
              Não foi possível buscar. Tente de novo.
            </p>
          )}
          {search.status === "done" && options.length === 0 && (
            <p role="status" className="px-3 py-2 text-sm text-muted">
              Nenhum resultado.
            </p>
          )}
          {options.length > 0 && (
            <ul id={listboxId} role="listbox" className="max-h-56 overflow-auto">
              {options.map((option, index) => (
                <li
                  key={option.id}
                  id={optionId(index)}
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
      )}
    </div>
  );
}

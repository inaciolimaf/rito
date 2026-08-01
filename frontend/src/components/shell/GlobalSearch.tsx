import { Search } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type FacetKey = "all" | "people" | "lawsuits";

const FACETS: { key: FacetKey; label: string }[] = [
  { key: "all", label: "Tudo" },
  { key: "people", label: "Pessoas" },
  { key: "lawsuits", label: "Processos" },
];

interface SearchResult {
  id: string;
  label: string;
  facet: Exclude<FacetKey, "all">;
  path: string;
}

// Backend real de busca fica para a spec 096 — esta lista é só para exercitar a UI
// (facetas + navegação por teclado) até lá.
const PLACEHOLDER_RESULTS: SearchResult[] = [
  { id: "1", label: "Ana Souza", facet: "people", path: "/customers" },
  { id: "2", label: "Bruno Lima", facet: "people", path: "/customers" },
  { id: "3", label: "0001234-56.2026.8.26.0100", facet: "lawsuits", path: "/lawsuits" },
];

function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}

export function GlobalSearch(): JSX.Element {
  const [facet, setFacet] = React.useState<FacetKey>("all");
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(-1);
  const [isFocused, setIsFocused] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const results = React.useMemo(() => {
    if (!query) return [];
    return PLACEHOLDER_RESULTS.filter((result) => facet === "all" || result.facet === facet).filter(
      (result) => result.label.toLowerCase().includes(query.toLowerCase()),
    );
  }, [facet, query]);

  React.useEffect(() => {
    function handleGlobalKeyDown(event: KeyboardEvent): void {
      if (event.key !== "/" || isTypingTarget(event.target)) return;
      event.preventDefault();
      inputRef.current?.focus();
    }
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, []);

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>): void {
    if (results.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) => Math.min(index + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      const result = results[activeIndex];
      if (result) {
        navigate(result.path);
        setQuery("");
        setIsFocused(false);
      }
    }
  }

  const listboxId = React.useId();
  const showPanel = isFocused && (query.length > 0 || results.length > 0);

  return (
    <div className="relative w-full max-w-md">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
        <Input
          ref={inputRef}
          value={query}
          placeholder="Buscar (pressione /)"
          className="pl-9"
          role="combobox"
          aria-expanded={showPanel}
          aria-controls={listboxId}
          aria-autocomplete="list"
          onFocus={() => setIsFocused(true)}
          onBlur={() => setTimeout(() => setIsFocused(false), 100)}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(-1);
          }}
          onKeyDown={handleKeyDown}
        />
      </div>

      {showPanel && (
        <div className="absolute top-full z-10 mt-1 w-full rounded border border-default bg-surface shadow-lg">
          <div className="flex gap-1 border-b border-default p-2">
            {FACETS.map((item) => (
              <button
                key={item.key}
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setFacet(item.key)}
                className={cn(
                  "rounded px-2 py-1 text-xs text-muted hover:text-primary",
                  facet === item.key && "bg-surface-muted text-primary",
                )}
              >
                {item.label}
              </button>
            ))}
          </div>
          <ul id={listboxId} role="listbox">
            {results.length === 0 ? (
              <li className="px-3 py-4 text-center text-sm text-muted">
                {query ? "Nenhum resultado." : "Digite para buscar."}
              </li>
            ) : (
              results.map((result, index) => (
                <li
                  key={result.id}
                  role="option"
                  aria-selected={index === activeIndex}
                  className={cn(
                    "cursor-pointer px-3 py-2 text-sm text-primary hover:bg-surface-muted",
                    index === activeIndex && "bg-surface-muted",
                  )}
                  onMouseDown={(event) => {
                    event.preventDefault();
                    navigate(result.path);
                    setQuery("");
                    setIsFocused(false);
                  }}
                >
                  {result.label}
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

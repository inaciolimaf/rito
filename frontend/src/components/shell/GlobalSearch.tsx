import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { Input } from "@/components/ui/input";
import { RecentSearches } from "@/features/search/RecentSearches";
import { SearchResultGroup } from "@/features/search/SearchResultGroup";
import {
  recordSearchClick,
  search,
  type SearchFacet,
  type SearchHitData,
  type SearchResponseData,
} from "@/features/search/api";
import { useDebounced } from "@/features/search/useDebounced";
import { cn } from "@/lib/utils";

const FACETS: { key: SearchFacet; label: string }[] = [
  { key: "all", label: "Tudo" },
  { key: "people", label: "Pessoas" },
  { key: "lawsuits", label: "Processos" },
];

const MIN_QUERY_LENGTH = 2;

const VAZIO: SearchResponseData = {
  people: { items: [], total: 0 },
  lawsuits: { items: [], total: 0 },
  tasks: { items: [], total: 0 },
  took_ms: 0,
  query_kind: "too_short",
  recent: [],
};

interface FlatHit extends SearchHitData {
  type: "customer" | "lawsuit" | "post";
  path: string;
}

function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    (target instanceof HTMLElement && target.isContentEditable)
  );
}

function flatten(data: SearchResponseData): FlatHit[] {
  return [
    ...data.people.items.map((hit) => ({
      ...hit,
      type: "customer" as const,
      path: "/customers",
    })),
    ...data.lawsuits.items.map((hit) => ({
      ...hit,
      type: "lawsuit" as const,
      path: `/lawsuits/${hit.id}`,
    })),
    ...data.tasks.items.map((hit) => ({
      ...hit,
      type: "post" as const,
      path: `/posts/${hit.id}`,
    })),
  ];
}

/** Busca do header (spec 008 na UI, spec 096 no backend).
 *
 * O debounce de 250 ms (regra 7) é o que evita a tela piscar resultados fora de ordem
 * enquanto alguém digita — e o que impede seis consultas para uma palavra de seis letras.
 */
export function GlobalSearch(): JSX.Element {
  const [facet, setFacet] = React.useState<SearchFacet>("all");
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(-1);
  const [isFocused, setIsFocused] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const debounced = useDebounced(query);

  const { data = VAZIO } = useQuery({
    queryKey: ["search", debounced, facet],
    queryFn: () => search(debounced, facet),
    enabled: isFocused,
    // Resultado de busca envelhece rápido: o cadastro criado há dez segundos precisa
    // aparecer, e a resposta é barata.
    staleTime: 0,
  });

  const results = React.useMemo(() => flatten(data), [data]);
  const activeId = results[activeIndex]?.id ?? null;

  React.useEffect(() => {
    function handleGlobalKeyDown(event: KeyboardEvent): void {
      if (event.key !== "/" || isTypingTarget(event.target)) return;
      event.preventDefault();
      inputRef.current?.focus();
    }
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, []);

  function selecionar(hit: FlatHit): void {
    // Regra 8: o clique é o sinal que alimenta as recentes e a ordenação futura. Falhar
    // aqui não pode impedir a navegação — o registro é telemetria, não o objetivo.
    void recordSearchClick({ query: debounced, type: hit.type, id: hit.id }).catch(() => undefined);
    navigate(hit.path);
    setQuery("");
    setIsFocused(false);
  }

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
      const hit = results[activeIndex];
      if (hit) selecionar(hit);
    }
  }

  const listboxId = React.useId();
  const showPanel = isFocused;
  const curtoDemais = debounced.trim().length < MIN_QUERY_LENGTH;

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
            {curtoDemais ? (
              <RecentSearches items={data.recent} onPick={setQuery} />
            ) : results.length === 0 ? (
              <li className="px-3 py-4 text-center text-sm text-muted">Nenhum resultado.</li>
            ) : (
              <>
                <SearchResultGroup
                  title="Pessoas"
                  facet={data.people}
                  query={debounced}
                  activeId={activeId}
                  onSelect={(hit) => selecionar({ ...hit, type: "customer", path: "/customers" })}
                />
                <SearchResultGroup
                  title="Processos"
                  facet={data.lawsuits}
                  query={debounced}
                  activeId={activeId}
                  onSelect={(hit) =>
                    selecionar({ ...hit, type: "lawsuit", path: `/lawsuits/${hit.id}` })
                  }
                />
                <SearchResultGroup
                  title="Tarefas"
                  facet={data.tasks}
                  query={debounced}
                  activeId={activeId}
                  onSelect={(hit) => selecionar({ ...hit, type: "post", path: `/posts/${hit.id}` })}
                />
              </>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

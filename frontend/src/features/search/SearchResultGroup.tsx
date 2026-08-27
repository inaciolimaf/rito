import { SearchResultItem } from "@/features/search/SearchResultItem";
import type { FacetData, SearchHitData } from "@/features/search/api";

export interface SearchResultGroupProps {
  title: string;
  facet: FacetData;
  query: string;
  activeId: string | null;
  onSelect: (hit: SearchHitData) => void;
}

/** Um grupo de resultados (spec 096 §6).
 *
 * O total aparece no cabeçalho porque a resposta rápida traz no máximo dez (regra 5): sem
 * o número, "10 processos" e "10 de 340 processos" seriam indistinguíveis, e a pessoa
 * pararia de procurar achando que viu tudo. */
export function SearchResultGroup({
  title,
  facet,
  query,
  activeId,
  onSelect,
}: SearchResultGroupProps): JSX.Element | null {
  if (facet.items.length === 0) return null;
  return (
    <li>
      <div className="flex items-center justify-between px-3 pt-2 text-xs text-muted">
        <span>{title}</span>
        {facet.total > facet.items.length && <span>{facet.total} no total</span>}
      </div>
      <ul>
        {facet.items.map((hit) => (
          <SearchResultItem
            key={hit.id}
            hit={hit}
            query={query}
            isActive={hit.id === activeId}
            onSelect={() => onSelect(hit)}
          />
        ))}
      </ul>
    </li>
  );
}

import type { SearchHitData } from "@/features/search/api";
import { cn } from "@/lib/utils";

export interface SearchResultItemProps {
  hit: SearchHitData;
  query: string;
  isActive: boolean;
  onSelect: () => void;
}

/** Um resultado, com o termo em destaque (spec 096 §6).
 *
 * O destaque existe para responder "por que ISSO apareceu?" — num resultado que casou
 * pelo CPF ou pela pasta, o nome sozinho não explica nada, e a pessoa desconfia da
 * busca. */
export function SearchResultItem({
  hit,
  query,
  isActive,
  onSelect,
}: SearchResultItemProps): JSX.Element {
  return (
    <li
      role="option"
      aria-selected={isActive}
      className={cn(
        "cursor-pointer px-3 py-2 text-sm text-primary hover:bg-surface-muted",
        isActive && "bg-surface-muted",
      )}
      onMouseDown={(event) => {
        event.preventDefault();
        onSelect();
      }}
    >
      <span>{highlight(hit.label, query)}</span>
      {hit.sublabel && <span className="block text-xs text-muted">{hit.sublabel}</span>}
    </li>
  );
}

/** Divide o texto no termo buscado e devolve os pedaços, com o trecho casado em
 * `<mark>`. Sem acento e sem diferenciar maiúscula, porque é assim que o servidor
 * procurou — destacar diferente de como se buscou confundiria mais que ajudar. */
export function highlight(text: string, query: string): React.ReactNode {
  const termo = query.trim();
  if (termo.length < 2) return text;
  const normalizado = normalize(text);
  const alvo = normalize(termo);
  const inicio = normalizado.indexOf(alvo);
  if (inicio < 0) return text;
  return (
    <>
      {text.slice(0, inicio)}
      <mark className="bg-warning/40 text-primary">{text.slice(inicio, inicio + alvo.length)}</mark>
      {text.slice(inicio + alvo.length)}
    </>
  );
}

function normalize(value: string): string {
  return value.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

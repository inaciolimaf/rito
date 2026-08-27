export interface RecentSearchesProps {
  items: string[];
  onPick: (query: string) => void;
}

/** As buscas recentes (spec 096, regras 1 e 12).
 *
 * Aparecem quando ainda não há o que buscar — abaixo de dois caracteres. É o único
 * conteúdo útil possível nesse momento: uma tela vazia dizendo "digite para buscar" não
 * ajuda ninguém que já usou o sistema ontem. */
export function RecentSearches({ items, onPick }: RecentSearchesProps): JSX.Element {
  if (items.length === 0) {
    return <li className="px-3 py-4 text-center text-sm text-muted">Digite para buscar.</li>;
  }
  return (
    <li aria-label="Buscas recentes">
      <div className="px-3 pt-2 text-xs text-muted">Buscas recentes</div>
      <ul>
        {items.map((item) => (
          <li key={item}>
            <button
              type="button"
              className="w-full px-3 py-2 text-left text-sm text-primary hover:bg-surface-muted"
              onMouseDown={(event) => {
                event.preventDefault();
                onPick(item);
              }}
            >
              {item}
            </button>
          </li>
        ))}
      </ul>
    </li>
  );
}

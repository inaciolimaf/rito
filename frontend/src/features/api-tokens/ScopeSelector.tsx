import type { ScopeData } from "@/features/api-tokens/api";

export interface ScopeSelectorProps {
  scopes: ScopeData[];
  selected: string[];
  onChange: (scopes: string[]) => void;
}

/** Escolha de escopos (spec 095, regra 2).
 *
 * Agrupado por recurso e com leitura separada de escrita, porque a decisão que a pessoa
 * está tomando é "este script pode MEXER nos meus processos?" — e um checkbox por linha
 * numa lista alfabética esconderia exatamente essa pergunta. */
export function ScopeSelector({ scopes, selected, onChange }: ScopeSelectorProps): JSX.Element {
  const porRecurso = new Map<string, ScopeData[]>();
  for (const item of scopes) {
    const recurso = item.scope.split(":")[1] ?? item.scope;
    porRecurso.set(recurso, [...(porRecurso.get(recurso) ?? []), item]);
  }

  function toggle(scope: string): void {
    onChange(
      selected.includes(scope) ? selected.filter((item) => item !== scope) : [...selected, scope],
    );
  }

  return (
    <div className="space-y-2" aria-label="Escopos do token">
      {[...porRecurso.entries()].map(([recurso, itens]) => (
        <div key={recurso} className="flex items-center gap-4">
          <span className="w-32 text-xs capitalize text-muted">{recurso}</span>
          {itens.map((item) => (
            <label key={item.scope} className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                aria-label={item.scope}
                checked={selected.includes(item.scope)}
                onChange={() => toggle(item.scope)}
              />
              {item.scope.startsWith("read:") ? "ler" : "escrever"}
            </label>
          ))}
        </div>
      ))}
    </div>
  );
}

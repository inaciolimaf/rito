import { useQuery } from "@tanstack/react-query";

import { StatCard } from "@/components/domain/StatCard";
import { getApiUsage } from "@/features/api-tokens/api";

/** Uso da API pública (spec 095, regra 9).
 *
 * Por rota, não por token: a pergunta operacional é "quem está batendo no limite?", e o
 * limite é por rota. */
export function ApiUsagePanel(): JSX.Element {
  const { data, isLoading } = useQuery({ queryKey: ["api-usage"], queryFn: () => getApiUsage() });
  const items = data?.items ?? [];

  return (
    <section className="space-y-2" aria-label="Uso da API">
      <h2 className="text-sm font-semibold text-primary">Uso nos últimos 7 dias</h2>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <StatCard label="Chamadas" value={data?.total_calls ?? 0} isLoading={isLoading} />
        <StatCard
          label="Erros"
          value={items.reduce((total, item) => total + item.errors, 0)}
          isLoading={isLoading}
        />
        <StatCard label="Rotas usadas" value={items.length} isLoading={isLoading} />
      </div>
      {items.length > 0 && (
        <ul className="space-y-1">
          {items.map((item) => (
            <li key={`${item.method}-${item.path}`} className="text-xs text-muted">
              <code>
                {item.method} {item.path}
              </code>{" "}
              — {item.calls} chamada(s)
              {item.errors > 0 && `, ${item.errors} com erro`}
              {item.avg_duration_ms !== null && `, ${item.avg_duration_ms} ms em média`}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

import type { ConversionGroupData } from "@/features/reports/api";

export interface ConversionFunnelProps {
  groups: ConversionGroupData[];
  isLoading?: boolean;
}

/** Funil de conversão por grupo de ação (spec 074, regra 7): oportunidades da coorte
 * → fechados, com a taxa ao lado. Regra 10: grupo sem movimento aparece zerado;
 * regra 11: sem oportunidades a taxa é "—", nunca 0%. */
export function ConversionFunnel({
  groups,
  isLoading = false,
}: ConversionFunnelProps): JSX.Element {
  const max = Math.max(1, ...groups.map((group) => group.opportunities));

  return (
    <section aria-label="Funil de conversão por grupo de ação" className="space-y-2">
      <h3 className="text-sm font-medium text-primary">Conversão por grupo de ação</h3>
      {isLoading ? (
        <div className="h-24 animate-pulse rounded bg-surface-muted" />
      ) : groups.length === 0 ? (
        <p className="text-sm text-muted">Nenhum grupo de ação cadastrado.</p>
      ) : (
        <ul className="space-y-1.5">
          {groups.map((group) => (
            <li key={group.action_group_id} className="flex items-center gap-2 text-sm">
              <span className="w-32 shrink-0 truncate text-muted">{group.action_group_name}</span>
              <span className="flex-1 rounded bg-surface-muted">
                <span
                  className="block h-4 rounded bg-accent"
                  style={{ width: `${(group.opportunities / max) * 100}%` }}
                />
              </span>
              <span className="w-40 shrink-0 text-right text-primary">
                {group.closed}/{group.opportunities} (
                {group.conversion_rate === null ? "—" : `${group.conversion_rate}%`})
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

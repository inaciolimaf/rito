import type { CycleAveragesData, TimeFeesGroupData } from "@/features/reports/api";

export interface CycleBarChartProps {
  groups: TimeFeesGroupData[];
}

interface CycleSeriesDef {
  key: keyof CycleAveragesData;
  label: string;
  color: string;
}

/** As 4 séries do gráfico de ciclos (spec 076 §6), nas cores fixas da spec: verde
 * prospecção, azul claro produção, azul escuro execução, vermelho rotação completa. */
export const CYCLE_SERIES: readonly CycleSeriesDef[] = [
  { key: "prospecting_days", label: "Prospecção", color: "#16a34a" },
  { key: "production_days", label: "Produção", color: "#38bdf8" },
  { key: "execution_days", label: "Execução", color: "#1e3a8a" },
  { key: "full_cycle_days", label: "Rotação completa", color: "#dc2626" },
];

/** Gráfico dos 4 ciclos lado a lado por grupo de ação (spec 076, regra 10). Barras
 * agrupadas em SVG puro: o BarChart de domínio só tem uma série por rótulo (mesmo
 * motivo pelo qual a 075 escreveu o SuccessTrendChart à parte). Ciclo nulo (regra 2:
 * data faltando) vira lacuna com "—" no rótulo, nunca barra de altura zero. */
export function CycleBarChart({ groups }: CycleBarChartProps): JSX.Element {
  const width = 480;
  const height = 160;
  const maxDays = Math.max(
    1,
    ...groups.flatMap((group) => CYCLE_SERIES.map((series) => group.cycles[series.key] ?? 0)),
  );
  const groupWidth = width / Math.max(1, groups.length);
  const barWidth = groupWidth / (CYCLE_SERIES.length + 1);

  return (
    <section aria-label="Ciclos por grupo de ação" className="space-y-2">
      <h3 className="text-sm font-medium text-primary">Tempo médio por grupo de ação (dias)</h3>
      {groups.length === 0 ? (
        <p className="text-sm text-muted">Nenhum processo fechado ainda.</p>
      ) : (
        <>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="h-44 w-full"
            role="img"
            aria-label="Ciclos médios por grupo de ação"
            data-testid="cycle-bar-chart"
          >
            {groups.map((group, groupIndex) =>
              CYCLE_SERIES.map((series, seriesIndex) => {
                const days = group.cycles[series.key];
                // Regra 2: ciclo nulo é lacuna — zero seria "no mesmo dia".
                if (days === null) return null;
                const barHeight = (days / maxDays) * (height - 20);
                return (
                  <rect
                    key={`${group.action_group_id}-${series.key}`}
                    x={groupIndex * groupWidth + seriesIndex * barWidth + 1}
                    y={height - 20 - barHeight}
                    width={Math.max(1, barWidth - 2)}
                    height={barHeight}
                    fill={series.color}
                  >
                    <title>
                      {group.action_group_name} — {series.label}: {days}d
                    </title>
                  </rect>
                );
              }),
            )}
            {groups.map((group, groupIndex) => (
              <text
                key={group.action_group_id}
                x={groupIndex * groupWidth + groupWidth / 2}
                y={height - 6}
                textAnchor="middle"
                className="fill-muted text-[10px]"
              >
                {group.action_group_name}
              </text>
            ))}
          </svg>
          <ul className="flex flex-wrap gap-3 text-xs text-muted">
            {CYCLE_SERIES.map((series) => (
              <li key={series.key} className="flex items-center gap-1">
                <span
                  className="inline-block h-3 w-3 rounded-sm"
                  style={{ backgroundColor: series.color }}
                />
                {series.label}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

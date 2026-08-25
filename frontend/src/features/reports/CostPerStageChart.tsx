import type { CostStageItemData } from "@/features/reports/api";
import { CYCLE_SERIES } from "@/features/reports/CycleBarChart";
import { formatBrl } from "@/lib/money";

export interface CostPerStageChartProps {
  stages: CostStageItemData[];
}

/** A cor de cada etapa é a do ciclo homônimo da 076 (spec 077, regra 10 —
 * consistência visual entre as abas): verde prospecção, azul claro produção, azul
 * escuro execução, vermelho rotação completa. */
const STAGE_ORDER = ["prospecting", "production", "execution", "full_cycle"] as const;

function stageColor(stage: string): string {
  const index = STAGE_ORDER.indexOf(stage as (typeof STAGE_ORDER)[number]);
  return (index >= 0 ? CYCLE_SERIES[index]?.color : undefined) ?? "#6b7280";
}

/** Gráfico de tempo médio por etapa do ciclo (spec 077 §2 e regra 10), com o custo
 * médio proporcional no tooltip de cada barra. Barras em SVG puro, mesmo idioma do
 * CycleBarChart da 076; etapa sem processo (null) vira lacuna com "—", nunca barra de
 * altura zero (regra 8). */
export function CostPerStageChart({ stages }: CostPerStageChartProps): JSX.Element {
  const width = 480;
  const height = 160;
  const maxDays = Math.max(1, ...stages.map((stage) => stage.avg_days ?? 0));
  const barWidth = width / (stages.length * 2 + 1);

  return (
    <section aria-label="Tempo e custo por etapa" className="space-y-2">
      <h3 className="text-sm font-medium text-primary">Tempo médio por etapa (dias)</h3>
      {stages.length === 0 ? (
        <p className="text-sm text-muted">Nenhum processo no recorte.</p>
      ) : (
        <>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="h-44 w-full"
            role="img"
            aria-label="Tempo médio por etapa do ciclo"
            data-testid="cost-per-stage-chart"
          >
            {stages.map((stage, index) => {
              // Regra 8: etapa sem processo é lacuna — zero seria "instantâneo".
              if (stage.avg_days === null) return null;
              const barHeight = (stage.avg_days / maxDays) * (height - 40);
              return (
                <rect
                  key={stage.stage}
                  x={(2 * index + 1) * barWidth}
                  y={height - 40 - barHeight}
                  width={Math.max(1, barWidth - 2)}
                  height={barHeight}
                  fill={stageColor(stage.stage)}
                >
                  <title>
                    {stage.label}: {stage.avg_days}d
                    {stage.avg_cost === null
                      ? " — custo —"
                      : ` — custo médio ${formatBrl(stage.avg_cost)}`}
                  </title>
                </rect>
              );
            })}
            {stages.map((stage, index) => (
              <text
                key={stage.stage}
                x={(2 * index + 1) * barWidth + barWidth / 2}
                y={height - 24}
                textAnchor="middle"
                className="fill-muted text-[10px]"
              >
                {stage.label}
              </text>
            ))}
            {stages.map((stage, index) => (
              <text
                key={`${stage.stage}-value`}
                x={(2 * index + 1) * barWidth + barWidth / 2}
                y={height - 10}
                textAnchor="middle"
                className="fill-muted text-[10px]"
              >
                {stage.avg_days === null ? "—" : `${stage.avg_days}d`}
              </text>
            ))}
          </svg>
          <ul className="flex flex-wrap gap-3 text-xs text-muted">
            {stages.map((stage) => (
              <li key={stage.stage} className="flex items-center gap-1">
                <span
                  className="inline-block h-3 w-3 rounded-sm"
                  style={{ backgroundColor: stageColor(stage.stage) }}
                />
                {stage.label}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

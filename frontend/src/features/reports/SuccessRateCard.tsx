import type { SuccessRateGroupData, SuccessTrendPointData } from "@/features/reports/api";

export interface SuccessRateCardProps {
  group: SuccessRateGroupData;
  /** Série de 24 meses do grupo (regra 6) — alimenta o sparkline. */
  trend: SuccessTrendPointData[];
  /** Regra 2: o critério da taxa, explicado no tooltip ao lado do valor. */
  rateNote: string;
}

/** Sparkline em SVG puro (sem lib — mesma decisão do BarChart de domínio): 24 barras,
 * uma por mês; mês sem concluídos (taxa null) vira lacuna, nunca barra em zero. */
function Sparkline({ points }: { points: SuccessTrendPointData[] }): JSX.Element {
  const width = 96;
  const height = 24;
  const barWidth = width / Math.max(1, points.length);
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-6 w-24"
      role="img"
      aria-label="Taxa de sucesso dos últimos 24 meses"
      data-testid="success-sparkline"
    >
      {points.map((point, index) =>
        point.success_rate === null ? null : (
          <rect
            key={point.month}
            x={index * barWidth}
            y={height - (point.success_rate / 100) * height}
            width={Math.max(1, barWidth - 1)}
            height={(point.success_rate / 100) * height}
            className="fill-accent"
          />
        ),
      )}
    </svg>
  );
}

/** Card de taxa de sucesso de um grupo de ação (spec 075 §6): taxa do mês com
 * sparkline de 24 meses (regra 6), tooltip com o critério (regra 2: acordo entra no
 * denominador, não no numerador), aviso de amostra pequena (regra 5) e "—" quando não
 * há concluídos (regra 11). */
export function SuccessRateCard({ group, trend, rateNote }: SuccessRateCardProps): JSX.Element {
  return (
    <div className="rounded border border-default bg-surface p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm text-muted">{group.action_group_name}</span>
        <Sparkline points={trend} />
      </div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="text-xl font-semibold text-primary">
          {group.success_rate === null ? "—" : `${group.success_rate}%`}
        </span>
        <span
          className="cursor-help text-xs text-muted"
          title={rateNote}
          data-testid="success-rate-tooltip"
          aria-label="Como a taxa é calculada"
        >
          ⓘ
        </span>
      </div>
      <p className="text-xs text-muted">
        {group.won} ganhos · {group.lost} perdidos · {group.settled} acordos
      </p>
      {group.small_sample && (
        <p className="mt-1 text-xs text-warning" role="note">
          Amostra pequena: menos de 10 processos concluídos — a taxa pode não significar nada.
        </p>
      )}
    </div>
  );
}

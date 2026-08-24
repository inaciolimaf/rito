import type { SuccessTrendPointData } from "@/features/reports/api";

export interface SuccessTrendChartProps {
  points: SuccessTrendPointData[];
}

function monthLabel(isoMonth: string): string {
  const [year, month] = isoMonth.split("-");
  return `${month}/${year}`;
}

/** Evolução da taxa de sucesso mês a mês (spec 075, regra 6: últimos 24 meses por
 * padrão). Barras verticais em SVG puro; mês sem concluídos não tem taxa — aparece sem
 * barra e com "—" no rótulo de valor, nunca 0% (regra 11). O BarChart de domínio não
 * serve aqui porque seu valor é sempre numérico (mesmo motivo pelo qual a 074 escreveu
 * o ConversionFunnel à parte). */
export function SuccessTrendChart({ points }: SuccessTrendChartProps): JSX.Element {
  const width = 480;
  const height = 120;
  const barWidth = width / Math.max(1, points.length);

  return (
    <section aria-label="Evolução da taxa de sucesso" className="space-y-2">
      <h3 className="text-sm font-medium text-primary">
        Taxa de sucesso — últimos {points.length} meses
      </h3>
      {points.length === 0 ? (
        <p className="text-sm text-muted">Sem dados ainda.</p>
      ) : (
        <>
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="h-32 w-full"
            role="img"
            aria-label="Evolução mensal da taxa de sucesso"
          >
            {points.map((point, index) =>
              point.success_rate === null ? null : (
                <rect
                  key={point.month}
                  x={index * barWidth + 1}
                  y={height - (point.success_rate / 100) * height}
                  width={Math.max(1, barWidth - 2)}
                  height={(point.success_rate / 100) * height}
                  className="fill-accent"
                >
                  <title>
                    {monthLabel(point.month)}: {point.success_rate}%
                  </title>
                </rect>
              ),
            )}
          </svg>
          <div className="flex justify-between text-xs text-muted">
            <span>{monthLabel(points[0]?.month ?? "")}</span>
            <span>{monthLabel(points[points.length - 1]?.month ?? "")}</span>
          </div>
        </>
      )}
    </section>
  );
}

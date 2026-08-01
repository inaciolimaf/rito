export interface DonutChartDatum {
  label: string;
  value: number;
}

export interface DonutChartProps {
  data: DonutChartDatum[];
  title?: string;
}

const COLORS = [
  "hsl(var(--accent))",
  "hsl(220 70% 55%)",
  "hsl(160 60% 45%)",
  "hsl(30 90% 55%)",
  "hsl(280 60% 55%)",
  "hsl(0 70% 55%)",
  "hsl(190 70% 45%)",
  "hsl(50 80% 50%)",
  "hsl(320 60% 55%)",
  "hsl(100 50% 45%)",
  "hsl(var(--text-muted))",
];

const SIZE = 160;
const RADIUS = 60;
const STROKE = 24;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** Gráfico de donut simples em SVG puro (sem lib de gráficos — spec 019, seção 6). Cada
 * fatia é um segmento de `<circle>` com `stroke-dasharray`, girado para encaixar depois do
 * anterior. */
export function DonutChart({ data, title }: DonutChartProps): JSX.Element {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  let offset = 0;

  return (
    <div className="flex flex-col items-center gap-3">
      {title && <h3 className="text-sm font-medium text-primary">{title}</h3>}
      {total === 0 ? (
        <p className="text-sm text-muted">Sem dados ainda.</p>
      ) : (
        <div className="flex items-center gap-4">
          <svg
            width={SIZE}
            height={SIZE}
            viewBox={`0 0 ${SIZE} ${SIZE}`}
            role="img"
            aria-label={title ?? "Gráfico de donut"}
          >
            {data.map((item, index) => {
              const fraction = item.value / total;
              const dash = fraction * CIRCUMFERENCE;
              const segment = (
                <circle
                  key={item.label}
                  cx={SIZE / 2}
                  cy={SIZE / 2}
                  r={RADIUS}
                  fill="none"
                  stroke={COLORS[index % COLORS.length]}
                  strokeWidth={STROKE}
                  strokeDasharray={`${dash} ${CIRCUMFERENCE - dash}`}
                  strokeDashoffset={-offset}
                  transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
                />
              );
              offset += dash;
              return segment;
            })}
          </svg>
          <ul className="space-y-1 text-sm">
            {data.map((item, index) => (
              <li key={item.label} className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: COLORS[index % COLORS.length] }}
                  aria-hidden="true"
                />
                <span className="text-primary">{item.label}</span>
                <span className="text-muted">({item.value})</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

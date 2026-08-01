export interface BarChartDatum {
  label: string;
  value: number;
}

export interface BarChartProps {
  data: BarChartDatum[];
  title?: string;
}

/** Gráfico de barras horizontais em SVG puro (sem lib de gráficos — spec 019, seção 6). */
export function BarChart({ data, title }: BarChartProps): JSX.Element {
  const max = Math.max(1, ...data.map((item) => item.value));

  return (
    <div className="space-y-2">
      {title && <h3 className="text-sm font-medium text-primary">{title}</h3>}
      {data.length === 0 ? (
        <p className="text-sm text-muted">Sem dados ainda.</p>
      ) : (
        <ul className="space-y-1.5" role="img" aria-label={title ?? "Gráfico de barras"}>
          {data.map((item) => (
            <li key={item.label} className="flex items-center gap-2 text-sm">
              <span className="w-24 shrink-0 truncate text-muted">{item.label}</span>
              <span className="flex-1 rounded bg-surface-muted">
                <span
                  className="block h-4 rounded bg-accent"
                  style={{ width: `${(item.value / max) * 100}%` }}
                />
              </span>
              <span className="w-8 shrink-0 text-right text-primary">{item.value}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export interface CashFlowChartPoint {
  label: string;
  income: number;
  expense: number;
}

export interface CashFlowChartProps {
  data: CashFlowChartPoint[];
  title?: string;
}

/** Receitas × despesas por período, em barras SVG-free (mesma linha de `BarChart` —
 * spec 019 §6). Duas séries por período, então (diferente de `BarChart`) precisa de
 * legenda — regra 6 do design system de gráficos. */
export function CashFlowChart({ data, title }: CashFlowChartProps): JSX.Element {
  const max = Math.max(1, ...data.flatMap((point) => [point.income, point.expense]));

  return (
    <div className="space-y-2">
      {title && <h3 className="text-sm font-medium text-primary">{title}</h3>}
      <div className="flex items-center gap-4 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-success" aria-hidden="true" />
          Receitas
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-danger" aria-hidden="true" />
          Despesas
        </span>
      </div>
      {data.length === 0 ? (
        <p className="text-sm text-muted">Sem dados ainda.</p>
      ) : (
        <div
          className="flex items-end gap-3 overflow-x-auto pb-1"
          role="img"
          aria-label={title ?? "Receitas x despesas"}
        >
          {data.map((point) => (
            <div key={point.label} className="flex shrink-0 flex-col items-center gap-1">
              <div className="flex h-28 items-end gap-1">
                <div
                  className="w-2.5 rounded-t bg-success"
                  style={{ height: `${(point.income / max) * 100}%` }}
                  title={`Receitas: ${point.income}`}
                />
                <div
                  className="w-2.5 rounded-t bg-danger"
                  style={{ height: `${(point.expense / max) * 100}%` }}
                  title={`Despesas: ${point.expense}`}
                />
              </div>
              <span className="max-w-12 truncate text-[10px] text-muted">{point.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

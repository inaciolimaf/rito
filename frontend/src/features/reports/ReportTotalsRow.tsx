export interface ReportTotalsRowProps {
  pointsTotal: number;
}

/** Rodapé de soma de pontos (spec 072 regra 4) — só aparece em productivity/delayed_tasks. */
export function ReportTotalsRow({ pointsTotal }: ReportTotalsRowProps): JSX.Element {
  return (
    <div className="flex justify-end border-t border-default px-3 py-2 text-sm">
      <span className="text-muted">Total de pontos:</span>
      <span className="ml-2 font-medium text-primary">{pointsTotal}</span>
    </div>
  );
}

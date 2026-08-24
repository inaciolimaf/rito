import { BarChart } from "@/components/domain/BarChart";
import type { ClosedTrendPointData } from "@/features/reports/api";

export interface SixMonthTrendProps {
  points: ClosedTrendPointData[];
}

function monthLabel(isoMonth: string): string {
  const [year, month] = isoMonth.split("-");
  return `${month}/${year}`;
}

/** Evolução de fechamentos nos últimos 6 meses (spec 074, regra 5) — meses zerados
 * aparecem na série (o backend já os devolve), o BarChart só rotula MM/AAAA. */
export function SixMonthTrend({ points }: SixMonthTrendProps): JSX.Element {
  return (
    <BarChart
      title="Fechamentos — últimos 6 meses"
      data={points.map((point) => ({ label: monthLabel(point.month), value: point.closed }))}
    />
  );
}

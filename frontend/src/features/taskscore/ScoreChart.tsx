import { BarChart, type BarChartDatum } from "@/components/domain/BarChart";
import type { ScoreChartResponse } from "@/features/taskscore/api";

export interface ScoreChartProps {
  chart: ScoreChartResponse;
}

/** Gráfico Taskscore (ADVBOX 4.1, spec 039 §2): visão mensal compara mês atual ×
 * mês anterior × meta; visão diária mostra os pontos por dia do mês corrente. */
export function ScoreChart({ chart }: ScoreChartProps): JSX.Element {
  if (chart.granularity === "daily") {
    return <BarChart title="Pontos por dia no mês" data={chart.days} />;
  }

  const data: BarChartDatum[] = [
    { label: "Mês anterior", value: chart.previous },
    { label: "Mês atual", value: chart.current },
  ];
  if (chart.goal !== null) {
    data.push({ label: "Meta", value: chart.goal });
  }
  return <BarChart title="Mês atual × mês anterior × meta" data={data} />;
}

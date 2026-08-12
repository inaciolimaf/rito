import { BarChart } from "@/components/domain/BarChart";
import type { AgingBucketData } from "@/features/financial/dunning-api";
import { formatBrl } from "@/lib/money";

const BUCKET_LABELS: Record<string, string> = {
  "1-15": "1–15 dias",
  "16-30": "16–30 dias",
  "31-60": "31–60 dias",
  "61-90": "61–90 dias",
  "90+": "90+ dias",
};

export interface AgingChartProps {
  data: AgingBucketData[];
}

/** Total atrasado por faixa de aging (spec 061, regra 2/11) — wrapper fino sobre
 * `BarChart` (regra dos 3 usos: nenhuma feature reinventa a barra). */
export function AgingChart({ data }: AgingChartProps): JSX.Element {
  return (
    <BarChart
      title="Atrasados por faixa"
      data={data.map((item) => ({
        label: BUCKET_LABELS[item.bucket] ?? item.bucket,
        value: item.total,
      }))}
      formatValue={formatBrl}
    />
  );
}

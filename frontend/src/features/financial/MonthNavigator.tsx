import { ChevronLeft, ChevronRight } from "lucide-react";

const MONTH_LABELS = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
];

export interface MonthNavigatorProps {
  /** "YYYY-MM" */
  month: string;
  onChange: (month: string) => void;
}

function parseMonth(month: string): { year: number; monthNumber: number } {
  const [yearPart, monthPart] = month.split("-");
  return { year: Number(yearPart ?? 0), monthNumber: Number(monthPart ?? 1) };
}

function shift(month: string, delta: number): string {
  const { year, monthNumber } = parseMonth(month);
  const zeroBased = monthNumber - 1 + delta;
  const nextYear = year + Math.floor(zeroBased / 12);
  const nextMonth = ((zeroBased % 12) + 12) % 12;
  return `${nextYear}-${String(nextMonth + 1).padStart(2, "0")}`;
}

/** Regra 8: navegar por mês preserva regime e filtros — o componente só troca o
 * parâmetro `month` da URL, quem monta a query é `FinancialDashboard`. */
export function MonthNavigator({ month, onChange }: MonthNavigatorProps): JSX.Element {
  const { year, monthNumber } = parseMonth(month);
  const label = `${MONTH_LABELS[monthNumber - 1]} de ${year}`;

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        aria-label="Mês anterior"
        className="rounded border border-default p-1.5 text-muted hover:text-primary"
        onClick={() => onChange(shift(month, -1))}
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      <span className="min-w-32 text-center text-sm font-medium text-primary">{label}</span>
      <button
        type="button"
        aria-label="Próximo mês"
        className="rounded border border-default p-1.5 text-muted hover:text-primary"
        onClick={() => onChange(shift(month, 1))}
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
}

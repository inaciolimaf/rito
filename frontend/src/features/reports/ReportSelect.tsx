import type { ReportKey } from "@/features/reports/api";
import { REPORT_OPTIONS } from "@/features/reports/reportDefinitions";

export interface ReportSelectProps {
  value: ReportKey;
  onChange: (value: ReportKey) => void;
}

/** Seletor dos 9 relatórios tabulares (spec 072 §6) — a lista vem de metadados, não de
 * 9 opções escritas à mão. */
export function ReportSelect({ value, onChange }: ReportSelectProps): JSX.Element {
  return (
    <label className="flex items-center gap-2 text-sm text-muted">
      Relatório
      <select
        className="rounded border border-default bg-surface px-2 py-1 text-sm text-primary"
        value={value}
        onChange={(event) => onChange(event.target.value as ReportKey)}
      >
        {REPORT_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

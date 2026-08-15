export interface ReportSelectOption {
  value: string;
  label: string;
}

export interface ReportSelectProps {
  value: string;
  options: ReportSelectOption[];
  onChange: (value: string) => void;
}

/** Seletor de relatório (spec 072 §6) — a lista vem de metadados, não de opções
 * escritas à mão. Genérico em `string` porque a página combina os 9 relatórios
 * tabulares com o livro de ponto (spec 073), que não é um `report_key` da 072. */
export function ReportSelect({ value, options, onChange }: ReportSelectProps): JSX.Element {
  return (
    <label className="flex items-center gap-2 text-sm text-muted">
      Relatório
      <select
        className="rounded border border-default bg-surface px-2 py-1 text-sm text-primary"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

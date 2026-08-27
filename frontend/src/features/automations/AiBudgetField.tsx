import * as React from "react";

export interface AiBudgetFieldProps {
  budgetUsd: number | null;
  spentUsd: number;
  onSave: (value: string | null) => void;
}

/** Teto de IA desta automação (spec 094, regra 6).
 *
 * Fica junto da automação, e não só nas configurações gerais de IA, porque protege de
 * outra coisa: o teto do escritório (spec 090) evita a conta surpresa; este evita que UMA
 * regra mal escrita — a que roda em toda intimação — consuma o mês inteiro sozinha. */
export function AiBudgetField({ budgetUsd, spentUsd, onSave }: AiBudgetFieldProps): JSX.Element {
  const [valor, setValor] = React.useState(budgetUsd === null ? "" : String(budgetUsd));

  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="flex flex-col text-xs text-muted">
        Teto de IA desta automação (US$/mês)
        <input
          aria-label="Teto de IA da automação"
          className="mt-1 w-28 rounded border border-default bg-surface p-1 text-sm"
          inputMode="decimal"
          placeholder="sem teto"
          value={valor}
          onChange={(event) => setValor(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="rounded border border-default px-2 py-1 text-xs"
        onClick={() => onSave(valor.trim() === "" ? null : valor.trim())}
      >
        Salvar teto
      </button>
      <span className="text-xs text-muted">
        Gasto no mês: US$ {spentUsd.toFixed(4)}
        {budgetUsd !== null && ` de US$ ${budgetUsd.toFixed(2)}`}
      </span>
    </div>
  );
}

import type { Regime } from "@/features/financial/api";

const REGIME_LABELS: Record<Regime, string> = {
  due: "Data de vencimento",
  payment: "Data de pagamento",
  competence: "Competência",
  cash_flow: "Fluxo de caixa",
};

export interface RegimeSelectProps {
  value: Regime;
  onChange: (value: Regime) => void;
}

/** Regra 1 (spec 059): os 4 regimes mudam qual data filtra o dashboard. */
export function RegimeSelect({ value, onChange }: RegimeSelectProps): JSX.Element {
  return (
    <select
      aria-label="Regime de visualização"
      className="h-10 rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      value={value}
      onChange={(event) => onChange(event.target.value as Regime)}
    >
      {Object.entries(REGIME_LABELS).map(([key, label]) => (
        <option key={key} value={key}>
          {label}
        </option>
      ))}
    </select>
  );
}

import { Checkbox } from "@/components/ui/checkbox";

export interface AutoReadToggleProps {
  enabled: boolean;
  disabled?: boolean;
  onChange: (enabled: boolean) => void;
}

/** Leitura automática das intimações novas (spec 086, regra 10).
 *
 * Desligada por padrão, e o texto diz por quê: cada análise consome tokens, e ninguém
 * deve descobrir isso na fatura. */
export function AutoReadToggle({
  enabled,
  disabled = false,
  onChange,
}: AutoReadToggleProps): JSX.Element {
  return (
    <label className="flex items-start justify-between gap-4 rounded border border-default bg-surface p-4">
      <span>
        <span className="block font-medium text-primary">
          Analisar intimações novas automaticamente
        </span>
        <span className="block text-sm text-muted">
          A IA lê, resume e sugere o prazo assim que a intimação chega. Cada análise consome tokens
          — o consumo aparece em Configurações &gt; Inteligência artificial.
        </span>
      </span>
      <Checkbox
        aria-label="Analisar intimações novas automaticamente"
        checked={enabled}
        disabled={disabled}
        onCheckedChange={(checked) => onChange(checked === true)}
      />
    </label>
  );
}

import type { ModelInfoData } from "@/features/ai/api";
import { describeModel } from "@/features/ai/pricing";

export interface ModelSelectProps {
  id: string;
  label: string;
  models: ModelInfoData[];
  value: string;
  onChange: (value: string) => void;
  /** O fallback pode ser "nenhum"; o modelo principal, não. */
  allowEmpty?: boolean;
  disabled?: boolean;
}

/** Seleção de modelo por feature (spec 081 §7): a escolha é do usuário, e o preço
 * aparece na hora de escolher — não na fatura. */
export function ModelSelect({
  id,
  label,
  models,
  value,
  onChange,
  allowEmpty = false,
  disabled = false,
}: ModelSelectProps): JSX.Element {
  const known = models.some((model) => model.id === value);
  return (
    <label className="block space-y-1" htmlFor={id}>
      <span className="text-sm text-muted">{label}</span>
      <select
        id={id}
        className="w-full rounded border border-default bg-surface p-2 text-sm"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        {allowEmpty && <option value="">Sem fallback</option>}
        {/* Modelo configurado que sumiu do catálogo continua selecionável — trocar por
            outro é decisão do escritório, não efeito colateral de abrir a tela. */}
        {!known && value !== "" && <option value={value}>{value} (fora do catálogo)</option>}
        {models.map((model) => (
          <option key={model.id} value={model.id}>
            {describeModel(model)}
          </option>
        ))}
      </select>
    </label>
  );
}

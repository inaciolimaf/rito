import * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { FeatureConfigData, FeatureConfigPayload, ModelInfoData } from "@/features/ai/api";
import { ModelSelect } from "@/features/ai/ModelSelect";

export interface FeatureConfigRowProps {
  config: FeatureConfigData;
  models: ModelInfoData[];
  onSave: (payload: FeatureConfigPayload) => Promise<unknown>;
}

/** Uma feature de IA e seu modelo (spec 081 §7). Cada linha salva sozinha: são
 * decisões independentes, e um erro numa não pode segurar as outras. */
export function FeatureConfigRow({ config, models, onSave }: FeatureConfigRowProps): JSX.Element {
  const [model, setModel] = React.useState(config.model);
  const [fallback, setFallback] = React.useState(config.fallback_model ?? "");
  const [temperature, setTemperature] = React.useState(String(config.temperature));
  const [isEnabled, setIsEnabled] = React.useState(config.is_enabled);
  const [storePrompts, setStorePrompts] = React.useState(config.store_prompts);
  const [saving, setSaving] = React.useState(false);

  async function handleSave(): Promise<void> {
    setSaving(true);
    try {
      await onSave({
        feature_key: config.feature_key,
        model,
        fallback_model: fallback === "" ? null : fallback,
        temperature: Number(temperature),
        max_tokens: config.max_tokens,
        is_enabled: isEnabled,
        store_prompts: storePrompts,
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section
      aria-label={config.label}
      className="space-y-3 rounded border border-default bg-surface p-4"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-medium text-primary">{config.label}</h3>
          <p className="text-sm text-muted">{config.description}</p>
          {config.is_default && (
            <p className="mt-1 text-xs text-warning">
              Ainda sem configuração própria — rodando com o modelo padrão do ambiente.
            </p>
          )}
        </div>
        <label className="flex items-center gap-2 text-sm text-muted">
          Ativa
          <Checkbox
            aria-label={`Ativar ${config.label}`}
            checked={isEnabled}
            onCheckedChange={(checked) => setIsEnabled(checked === true)}
          />
        </label>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <ModelSelect
          id={`model-${config.feature_key}`}
          label="Modelo"
          models={models}
          value={model}
          onChange={setModel}
        />
        <ModelSelect
          id={`fallback-${config.feature_key}`}
          label="Fallback"
          models={models}
          value={fallback}
          onChange={setFallback}
          allowEmpty
        />
        <div className="space-y-1">
          <Label htmlFor={`temp-${config.feature_key}`}>Temperatura</Label>
          <Input
            id={`temp-${config.feature_key}`}
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            onChange={(event) => setTemperature(event.target.value)}
          />
        </div>
      </div>

      <label className="flex items-center justify-between gap-4 text-sm">
        <span>
          <span className="block text-primary">Guardar prompt e resposta</span>
          <span className="block text-muted">
            Desligado por padrão (LGPD): sem isto, o Rito guarda só tokens, custo e latência.
          </span>
        </span>
        <Checkbox
          aria-label={`Guardar prompt e resposta de ${config.label}`}
          checked={storePrompts}
          onCheckedChange={(checked) => setStorePrompts(checked === true)}
        />
      </label>

      <div className="flex justify-end">
        <Button type="button" size="sm" disabled={saving || !model} onClick={handleSave}>
          Salvar
        </Button>
      </div>
    </section>
  );
}

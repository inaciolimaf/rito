import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listAiModels,
  listFeatureConfig,
  saveFeatureConfig,
  type FeatureConfigPayload,
} from "@/features/ai/api";
import { AiBudgetPanel } from "@/features/ai/AiBudgetPanel";
import { AiUsagePanel } from "@/features/ai/AiUsagePanel";
import { FeatureConfigRow } from "@/features/ai/FeatureConfigRow";
import { PendingActionsList } from "@/features/ai/PendingActionsList";

/** Configurações > Inteligência artificial (spec 081 §7). Uma tela, três perguntas:
 * qual modelo cada feature usa, o que isso está custando, e o que é guardado. */
export function AiSettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { data: catalog } = useQuery({ queryKey: ["ai-models"], queryFn: listAiModels });
  const { data: config, isLoading } = useQuery({
    queryKey: ["ai-feature-config"],
    queryFn: listFeatureConfig,
  });

  const save = useMutation({
    mutationFn: (payload: FeatureConfigPayload) => saveFeatureConfig(payload),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["ai-feature-config"] }).then(() => undefined),
  });

  const isConfigured = config?.is_configured ?? false;

  return (
    <div className="space-y-4 p-6">
      <div>
        <h1 className="text-lg font-semibold text-primary">Inteligência artificial</h1>
        <p className="text-sm text-muted">
          O Rito fala com os modelos por um único gateway (OpenRouter). O modelo de cada feature é
          escolha do escritório — trocar aqui muda a próxima chamada.
        </p>
      </div>

      {!isConfigured && (
        <p role="alert" className="rounded border border-warning bg-warning/10 p-3 text-sm">
          Nenhuma chave de IA configurada (<code>OPENROUTER_API_KEY</code>). As features de IA ficam
          desabilitadas até que o servidor tenha a chave — o resto do sistema segue normal, e a
          configuração abaixo já pode ser preenchida.
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-muted">Carregando configuração…</p>
      ) : (
        <div className="space-y-3">
          {(config?.items ?? []).map((item) => (
            <FeatureConfigRow
              key={item.feature_key}
              config={item}
              models={catalog?.items ?? []}
              onSave={(payload) => save.mutateAsync(payload)}
            />
          ))}
        </div>
      )}

      <section className="space-y-2" aria-label="Ações aguardando confirmação">
        <h2 className="text-sm font-semibold text-primary">Aguardando sua confirmação</h2>
        <p className="text-sm text-muted">
          A IA nunca grava sozinha: o que ela propôs espera aqui até alguém decidir.
        </p>
        <PendingActionsList />
      </section>

      <AiBudgetPanel />

      <AiUsagePanel />
    </div>
  );
}

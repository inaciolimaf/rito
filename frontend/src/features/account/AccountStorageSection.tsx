import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { updateAccountPlan } from "@/features/account/api";
import { getAccountStorage, type AccountPlan } from "@/features/documents/api";

const PLAN_LABELS: Record<AccountPlan, string> = {
  ESSENCIAL: "Essencial (50 GB)",
  BANCA_JURIDICA: "Banca Jurídica (70 GB)",
  BANCA_MAX: "Banca Max (90 GB)",
  ELITE: "Elite (100 GB)",
};

function formatGb(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

export interface AccountStorageSectionProps {
  disabled: boolean;
}

/** Painel de armazenamento (spec 063, regra 6/12) — usado × quota do plano, com troca
 * de plano restrita a Gestor. */
export function AccountStorageSection({ disabled }: AccountStorageSectionProps): JSX.Element {
  const queryClient = useQueryClient();
  const { data: storage, isLoading } = useQuery({
    queryKey: ["account-storage"],
    queryFn: getAccountStorage,
  });

  const changePlan = useMutation({
    mutationFn: updateAccountPlan,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["account-storage"] });
      void queryClient.invalidateQueries({ queryKey: ["account"] });
    },
  });

  if (isLoading || !storage) {
    return <p className="text-sm text-muted">Carregando armazenamento…</p>;
  }

  const percentUsed = Math.min(100, (storage.used_bytes / storage.quota_bytes) * 100);

  return (
    <div className="space-y-2 rounded border border-default bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-medium text-primary">Plano e armazenamento</h2>
        <select
          aria-label="Plano do escritório"
          className="h-9 rounded border border-default bg-surface px-2 text-sm text-primary disabled:opacity-50"
          value={storage.plan}
          disabled={disabled || changePlan.isPending}
          onChange={(event) => changePlan.mutate(event.target.value as AccountPlan)}
        >
          {Object.entries(PLAN_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      <div className="h-2 w-full overflow-hidden rounded bg-surface-muted">
        <div
          className="h-full bg-accent"
          style={{ width: `${percentUsed}%` }}
          role="progressbar"
          aria-valuenow={Math.round(percentUsed)}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      <p className="text-sm text-muted">
        {formatGb(storage.used_bytes)} de {formatGb(storage.quota_bytes)} usados
      </p>
    </div>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { AutomationBuilder } from "@/features/automations/AutomationBuilder";
import { AutomationTestDialog } from "@/features/automations/AutomationTestDialog";
import { RunsTimeline } from "@/features/automations/RunsTimeline";
import {
  createAutomation,
  deleteAutomation,
  listAutomations,
  toggleAutomation,
  type AutomationData,
  type AutomationPayload,
} from "@/features/automations/api";
import { TRIGGER_LABELS } from "@/features/automations/labels";
import { ApiError } from "@/lib/errors";

/** Configurações > Automações (spec 092 §6). */
export function AutomationsSettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [criando, setCriando] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);
  const [abertaId, setAbertaId] = React.useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["automations"],
    queryFn: () => listAutomations(),
  });

  const invalidar = () =>
    queryClient.invalidateQueries({ queryKey: ["automations"] }).then(() => undefined);

  const salvar = useMutation({
    mutationFn: (payload: AutomationPayload) => createAutomation(payload),
    onSuccess: () => {
      setCriando(false);
      setErro(null);
      void invalidar();
    },
    onError: (error: unknown) =>
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar."),
  });

  const alternar = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      toggleAutomation(id, isActive),
    onSuccess: () => void invalidar(),
  });

  const remover = useMutation({
    mutationFn: (id: string) => deleteAutomation(id),
    onSuccess: () => void invalidar(),
  });

  const items: AutomationData[] = data?.items ?? [];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold text-primary">Automações</h1>
          <p className="text-sm text-muted">
            Quando algo acontecer, o sistema faz o resto. As ações rodam na ordem em que aparecem,
            com as permissões de quem criou a regra.
          </p>
        </div>
        <button
          type="button"
          className="rounded bg-primary px-3 py-1 text-sm text-on-primary"
          onClick={() => setCriando((atual) => !atual)}
        >
          {criando ? "Cancelar" : "Nova automação"}
        </button>
      </div>

      {criando && (
        <AutomationBuilder
          onSave={(payload) => salvar.mutate(payload)}
          isSaving={salvar.isPending}
          error={erro}
        />
      )}

      {isLoading ? (
        <p className="text-sm text-muted">Carregando…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">
          Nenhuma automação ainda. A primeira costuma ser &ldquo;chegou intimação, avise o
          responsável&rdquo;.
        </p>
      ) : (
        <ul className="space-y-3">
          {items.map((automation) => (
            <li key={automation.id} className="rounded border border-default p-3">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-primary">{automation.name}</h2>
                  <p className="text-xs text-muted">
                    {TRIGGER_LABELS[automation.trigger_kind]} · {automation.actions.length}{" "}
                    ação(ões)
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <label className="flex items-center gap-1 text-xs text-muted">
                    <input
                      type="checkbox"
                      checked={automation.is_active}
                      onChange={(event) =>
                        alternar.mutate({ id: automation.id, isActive: event.target.checked })
                      }
                    />
                    Ativa
                  </label>
                  <button
                    type="button"
                    className="rounded border border-default px-2 py-1 text-xs"
                    onClick={() =>
                      setAbertaId((atual) => (atual === automation.id ? null : automation.id))
                    }
                  >
                    Histórico
                  </button>
                  <button
                    type="button"
                    className="rounded border border-default px-2 py-1 text-xs text-danger"
                    onClick={() => remover.mutate(automation.id)}
                  >
                    Excluir
                  </button>
                </div>
              </div>

              <div className="mt-2 space-y-2">
                <AutomationTestDialog automationId={automation.id} />
                {abertaId === automation.id && <RunsTimeline automationId={automation.id} />}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

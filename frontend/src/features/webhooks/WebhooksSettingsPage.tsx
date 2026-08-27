import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { DeliveryLog } from "@/features/webhooks/DeliveryLog";
import { SecretRevealOnce } from "@/features/webhooks/SecretRevealOnce";
import {
  createEndpoint,
  deleteEndpoint,
  listEndpoints,
  reactivateEndpoint,
  rotateSecret,
  testEndpoint,
  type WebhookEndpointData,
} from "@/features/webhooks/api";
import { ApiError } from "@/lib/errors";

/** Configurações > Webhooks (spec 093 §6). */
export function WebhooksSettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [nome, setNome] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [segredo, setSegredo] = React.useState<string | null>(null);
  const [erro, setErro] = React.useState<string | null>(null);
  const [abertoId, setAbertoId] = React.useState<string | null>(null);

  const { data, isLoading } = useQuery({ queryKey: ["webhooks"], queryFn: listEndpoints });
  const invalidar = () =>
    queryClient.invalidateQueries({ queryKey: ["webhooks"] }).then(() => undefined);

  const criar = useMutation({
    mutationFn: () => createEndpoint({ name: nome, url, headers: {} }),
    onSuccess: (endpoint) => {
      setSegredo(endpoint.secret);
      setNome("");
      setUrl("");
      setErro(null);
      void invalidar();
    },
    onError: (error: unknown) =>
      setErro(error instanceof ApiError ? error.message : "Não foi possível salvar."),
  });

  const rotacionar = useMutation({
    mutationFn: (id: string) => rotateSecret(id),
    onSuccess: (endpoint) => setSegredo(endpoint.secret),
  });
  const reativar = useMutation({
    mutationFn: (id: string) => reactivateEndpoint(id),
    onSuccess: () => void invalidar(),
  });
  const remover = useMutation({
    mutationFn: (id: string) => deleteEndpoint(id),
    onSuccess: () => void invalidar(),
  });
  const testar = useMutation({ mutationFn: (id: string) => testEndpoint(id) });

  const items: WebhookEndpointData[] = data?.items ?? [];

  return (
    <div className="space-y-4 p-6">
      <div>
        <h1 className="text-lg font-semibold text-primary">Webhooks</h1>
        <p className="text-sm text-muted">
          O Rito manda os eventos para o sistema que o escritório usar. Cada envio vai assinado, e o
          destino precisa ser HTTPS.
        </p>
      </div>

      {segredo && <SecretRevealOnce secret={segredo} onDismiss={() => setSegredo(null)} />}

      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          criar.mutate();
        }}
      >
        <label className="flex flex-col text-xs text-muted">
          Nome
          <input
            aria-label="Nome do webhook"
            className="mt-1 rounded border border-default bg-surface p-1 text-sm"
            value={nome}
            onChange={(event) => setNome(event.target.value)}
          />
        </label>
        <label className="flex flex-col text-xs text-muted">
          URL
          <input
            aria-label="URL do webhook"
            className="mt-1 w-80 rounded border border-default bg-surface p-1 text-sm"
            placeholder="https://..."
            value={url}
            onChange={(event) => setUrl(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="rounded bg-primary px-3 py-1 text-sm text-on-primary"
          disabled={criar.isPending || nome.trim().length < 2 || url.trim().length < 8}
        >
          Adicionar
        </button>
      </form>

      {erro && (
        <p role="alert" className="rounded border border-danger bg-danger/10 p-2 text-sm">
          {erro}
        </p>
      )}

      {isLoading ? (
        <p className="text-sm text-muted">Carregando…</p>
      ) : (
        <ul className="space-y-3">
          {items.map((endpoint) => (
            <li key={endpoint.id} className="rounded border border-default p-3">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-primary">{endpoint.name}</h2>
                  <p className="break-all text-xs text-muted">{endpoint.url}</p>
                </div>
                <div className="flex items-center gap-2">
                  {!endpoint.is_active && (
                    <button
                      type="button"
                      className="rounded border border-warning px-2 py-1 text-xs text-warning"
                      onClick={() => reativar.mutate(endpoint.id)}
                    >
                      Reativar
                    </button>
                  )}
                  <button
                    type="button"
                    className="rounded border border-default px-2 py-1 text-xs"
                    onClick={() => testar.mutate(endpoint.id)}
                  >
                    Testar
                  </button>
                  <button
                    type="button"
                    className="rounded border border-default px-2 py-1 text-xs"
                    onClick={() => rotacionar.mutate(endpoint.id)}
                  >
                    Novo segredo
                  </button>
                  <button
                    type="button"
                    className="rounded border border-default px-2 py-1 text-xs"
                    onClick={() =>
                      setAbertoId((atual) => (atual === endpoint.id ? null : endpoint.id))
                    }
                  >
                    Entregas
                  </button>
                  <button
                    type="button"
                    className="rounded border border-default px-2 py-1 text-xs text-danger"
                    onClick={() => remover.mutate(endpoint.id)}
                  >
                    Excluir
                  </button>
                </div>
              </div>

              {!endpoint.is_active && (
                <p className="mt-2 rounded border border-warning bg-warning/10 p-2 text-xs">
                  Desativado depois de {endpoint.failure_streak} falhas seguidas. Confira a URL
                  antes de reativar.
                </p>
              )}

              {abertoId === endpoint.id && (
                <div className="mt-2">
                  <DeliveryLog endpointId={endpoint.id} />
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

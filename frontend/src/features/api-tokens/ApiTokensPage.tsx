import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiUsagePanel } from "@/features/api-tokens/ApiUsagePanel";
import { CreateTokenDialog } from "@/features/api-tokens/CreateTokenDialog";
import { listApiTokens, revokeApiToken } from "@/features/api-tokens/api";

/** Configurações > API (spec 095 §6). */
export function ApiTokensPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["api-tokens"], queryFn: listApiTokens });

  const revogar = useMutation({
    mutationFn: (id: string) => revokeApiToken(id),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["api-tokens"] }).then(() => undefined),
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-4 p-6">
      <div>
        <h1 className="text-lg font-semibold text-primary">API</h1>
        <p className="text-sm text-muted">
          Tokens para integrar o Rito com outros sistemas. A documentação do contrato está em{" "}
          <code>/api/public/v1/openapi.json</code>.
        </p>
      </div>

      <CreateTokenDialog
        onCreated={() => void queryClient.invalidateQueries({ queryKey: ["api-tokens"] })}
      />

      {isLoading ? (
        <p className="text-sm text-muted">Carregando…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">Nenhum token criado ainda.</p>
      ) : (
        <ul className="space-y-2" aria-label="Tokens de API">
          {items.map((token) => (
            <li
              key={token.id}
              className="flex items-center justify-between rounded border border-default p-3"
            >
              <div>
                <h2 className="text-sm font-semibold text-primary">{token.name}</h2>
                <p className="text-xs text-muted">
                  <code>{token.prefix}…</code> · {token.scopes.join(", ")}
                </p>
                <p className="text-xs text-muted">
                  {token.last_used_at
                    ? `Usado pela última vez em ${new Date(token.last_used_at).toLocaleString("pt-BR")}`
                    : "Nunca usado"}
                </p>
              </div>
              {token.is_active ? (
                <button
                  type="button"
                  className="rounded border border-default px-2 py-1 text-xs text-danger"
                  onClick={() => revogar.mutate(token.id)}
                >
                  Revogar
                </button>
              ) : (
                <span className="text-xs text-muted">Revogado</span>
              )}
            </li>
          ))}
        </ul>
      )}

      <ApiUsagePanel />
    </div>
  );
}

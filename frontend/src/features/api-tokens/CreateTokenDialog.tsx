import { useMutation, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { ScopeSelector } from "@/features/api-tokens/ScopeSelector";
import { createApiToken, listScopes, type ApiTokenData } from "@/features/api-tokens/api";
import { ApiError } from "@/lib/errors";

export interface CreateTokenDialogProps {
  onCreated: () => void;
}

/** Criação de token (spec 095, regra 1).
 *
 * O token aparece UMA vez. O bloco que o mostra é deliberadamente incômodo — ocupa
 * espaço, exige um clique explícito para sumir e não volta: quem fechar sem copiar
 * precisa gerar outro, e isso é melhor que um segredo pendurado na tela até alguém tirar
 * print. Mesma decisão do segredo de webhook (spec 093). */
export function CreateTokenDialog({ onCreated }: CreateTokenDialogProps): JSX.Element {
  const [nome, setNome] = React.useState("");
  const [escopos, setEscopos] = React.useState<string[]>([]);
  const [criado, setCriado] = React.useState<ApiTokenData | null>(null);
  const [erro, setErro] = React.useState<string | null>(null);
  const [copiado, setCopiado] = React.useState(false);

  const { data: disponiveis = [] } = useQuery({ queryKey: ["api-scopes"], queryFn: listScopes });

  const criar = useMutation({
    mutationFn: () => createApiToken({ name: nome, scopes: escopos, allowed_ips: [] }),
    onSuccess: (token) => {
      setCriado(token);
      setNome("");
      setEscopos([]);
      setErro(null);
      onCreated();
    },
    onError: (error: unknown) =>
      setErro(error instanceof ApiError ? error.message : "Não foi possível criar o token."),
  });

  if (criado?.token) {
    return (
      <div
        role="alert"
        aria-label="Token gerado"
        className="space-y-2 rounded border border-warning bg-warning/10 p-3"
      >
        <p className="text-sm">
          Copie o token agora. Ele <strong>não será mostrado de novo</strong> — o Rito guarda apenas
          um hash.
        </p>
        <code className="block break-all rounded bg-surface p-2 text-xs">{criado.token}</code>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded border border-default px-2 py-1 text-xs"
            onClick={() => {
              void navigator.clipboard?.writeText(criado.token ?? "");
              setCopiado(true);
            }}
          >
            {copiado ? "Copiado" : "Copiar"}
          </button>
          <button
            type="button"
            className="rounded bg-primary px-2 py-1 text-xs text-on-primary"
            onClick={() => {
              setCriado(null);
              setCopiado(false);
            }}
          >
            Já guardei
          </button>
        </div>
      </div>
    );
  }

  return (
    <form
      className="space-y-3 rounded border border-default p-3"
      aria-label="Novo token de API"
      onSubmit={(event) => {
        event.preventDefault();
        criar.mutate();
      }}
    >
      <label className="flex flex-col text-xs text-muted">
        Nome do token
        <input
          aria-label="Nome do token"
          className="mt-1 rounded border border-default bg-surface p-1 text-sm"
          placeholder="Ex.: integração com o n8n"
          value={nome}
          onChange={(event) => setNome(event.target.value)}
        />
      </label>

      <ScopeSelector scopes={disponiveis} selected={escopos} onChange={setEscopos} />

      {erro && (
        <p role="alert" className="rounded border border-danger bg-danger/10 p-2 text-sm">
          {erro}
        </p>
      )}

      <button
        type="submit"
        className="rounded bg-primary px-3 py-1 text-sm text-on-primary"
        disabled={criar.isPending || nome.trim().length < 2 || escopos.length === 0}
      >
        Gerar token
      </button>
    </form>
  );
}

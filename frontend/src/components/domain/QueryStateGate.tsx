import * as React from "react";

import { EmptyState } from "@/components/domain/EmptyState";
import { describeFailure } from "@/lib/errors";
import { cn } from "@/lib/utils";

export interface QueryStateGateProps<TData> {
  /** `isLoading`/`isPending` da query. */
  isLoading: boolean;
  /** `error` da query — `unknown` de propósito: quem classifica é `describeFailure`. */
  error: unknown;
  data: TData | undefined | null;
  /** Texto do carregando. "Carregando processo…" diz mais que "Carregando…". */
  loadingLabel?: string;
  /** Refetch da query. Sem ele, o erro não oferece saída nenhuma. */
  onRetry?: () => void;
  /** O que mostrar quando a consulta terminou sem erro e sem dado. */
  emptyState?: React.ReactNode;
  /** Espaçamento dos estados. A tela inteira usa o padrão; um card dentro de uma tela
   * passa algo menor, para o erro não empurrar o resto da página. */
  className?: string;
  children: (data: TData) => React.ReactNode;
}

/** Estados obrigatórios de uma tela de detalhe: carregando, erro, **sem permissão** e
 * vazio (CLAUDE.md §6; spec 007, regra 7 — "nada acontece" não é estado).
 *
 * Existe por causa de um defeito repetido sete vezes: `if (isLoading || !data)` parece
 * cobrir tudo e não cobre nada. Quando a API falha, o TanStack Query devolve
 * `isLoading: false` com `data: undefined` — a condição continua verdadeira e a tela fica
 * em "Carregando…" para sempre, sem erro, sem botão, sem explicação. A ordem aqui é a
 * inversa da que causa o bug: **erro primeiro**, carregando depois. */
export function QueryStateGate<TData>({
  isLoading,
  error,
  data,
  loadingLabel = "Carregando…",
  onRetry,
  emptyState,
  className = "p-6",
  children,
}: QueryStateGateProps<TData>): JSX.Element {
  if (error != null) {
    const failure = describeFailure(error);
    return (
      <div className={className}>
        <EmptyState
          role="alert"
          title={failure.title}
          description={failure.description}
          // Não adianta oferecer "tentar de novo" para 403: tentar de novo dá 403 de novo.
          action={
            onRetry && failure.kind !== "forbidden"
              ? { label: "Tentar de novo", onClick: onRetry }
              : undefined
          }
        />
      </div>
    );
  }

  if (isLoading) {
    return (
      <p className={cn("text-sm text-muted", className)} role="status" aria-busy="true">
        {loadingLabel}
      </p>
    );
  }

  if (data == null) {
    return (
      <>
        {emptyState ?? (
          <div className={className}>
            <EmptyState title="Nada para mostrar." description="A consulta não devolveu dados." />
          </div>
        )}
      </>
    );
  }

  return <>{children(data)}</>;
}

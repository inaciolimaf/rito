import { useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ApiError } from "@/lib/errors";

export interface UseTransferBeforeDeleteOptions<TItem> {
  /** Chave de invalidação do React Query — a mesma da listagem. */
  queryKey: unknown[];
  remove: (item: TItem) => Promise<void>;
  transfer: (fromItem: TItem, destinationId: string) => Promise<void>;
  /** Invalidações extras: transferir move dado de OUTRO domínio (processos, contatos,
   * lançamentos), e a listagem daquele domínio também ficou velha. */
  alsoInvalidate?: unknown[][];
}

export interface UseTransferBeforeDeleteResult<TItem> {
  pendingTransfer: TItem | null;
  transferError: ApiError | null;
  dialogOpen: boolean;
  closeDialog: () => void;
  /** Tenta excluir. Se o backend responder 409 ("em uso"), abre o diálogo de
   * transferência em vez de propagar o erro. */
  requestDelete: (item: TItem) => Promise<void>;
  /** Transfere para o destino escolhido e então exclui. */
  transferAndDelete: (destinationId: string) => Promise<void>;
}

/** Spec 101, Bloco A: excluir uma taxonomia "em uso" exige transferir antes.
 *
 * A tela NÃO pergunta antes "quantos usam isto?" — ela tenta excluir e deixa o backend
 * responder. O 409 é a fonte de verdade (regras 1/3/7/11), e um contador na listagem
 * seria uma segunda fonte, que pode estar velha entre o render e o clique: com contagem
 * no front, dois usuários simultâneos veem "0 em uso" e um dos dois toma 500.
 *
 * É também o motivo de este fluxo não ter virado contador nas 4 telas novas: as duas
 * telas que já usavam `TransferBeforeDeleteDialog` (grupos de ação e tipos de tarefa,
 * spec 014/031) decidem pelo `*_count` que a API já devolvia; as quatro desta spec
 * decidem pelo status HTTP, sem endpoint novo nem query a mais na listagem.
 */
export function useTransferBeforeDelete<TItem>(
  options: UseTransferBeforeDeleteOptions<TItem>,
): UseTransferBeforeDeleteResult<TItem> {
  const queryClient = useQueryClient();
  const [pendingTransfer, setPendingTransfer] = React.useState<TItem | null>(null);
  const [transferError, setTransferError] = React.useState<ApiError | null>(null);

  async function invalidateAll(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: options.queryKey });
    for (const key of options.alsoInvalidate ?? []) {
      await queryClient.invalidateQueries({ queryKey: key });
    }
  }

  async function requestDelete(item: TItem): Promise<void> {
    setTransferError(null);
    try {
      await options.remove(item);
      await invalidateAll();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setPendingTransfer(item);
        return;
      }
      throw error;
    }
  }

  async function transferAndDelete(destinationId: string): Promise<void> {
    if (!pendingTransfer) return;
    try {
      await options.transfer(pendingTransfer, destinationId);
      await options.remove(pendingTransfer);
      setPendingTransfer(null);
      await invalidateAll();
    } catch (error) {
      setTransferError(error instanceof ApiError ? error : null);
      throw error;
    }
  }

  return {
    pendingTransfer,
    transferError,
    dialogOpen: pendingTransfer !== null,
    closeDialog: () => {
      setPendingTransfer(null);
      setTransferError(null);
    },
    requestDelete,
    transferAndDelete,
  };
}

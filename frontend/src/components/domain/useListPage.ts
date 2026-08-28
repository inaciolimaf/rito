import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import type { ListResponse } from "@/components/domain/types";
import { ApiError } from "@/lib/errors";

export interface UseListPageOptions<TFilters, TPage extends ListResponse<unknown>> {
  /** Chave estável da query (ex.: "lawsuits-list") — o export e o refresh a reutilizam. */
  queryKey: string;
  /** Filtros ativos (já extraídos da URL pela página via `useFilters`). */
  filters: TFilters;
  fetchPage: (params: TFilters & { cursor: string | undefined; limit: number }) => Promise<TPage>;
  /** Opcional: nem toda listagem exporta. A de lançamentos (056) não tem export, e
   * exigir um callback vazio dela seria fingir uma capacidade que a tela não oferece. */
  exportFile?: (format: "xlsx" | "pdf", filters: TFilters) => Promise<void>;
  /** Quando qualquer um destes valores muda, a paginação volta para a primeira página. */
  resetDeps: readonly unknown[];
  limit?: number;
}

export interface UseListPageResult<TPage extends ListResponse<unknown>> {
  items: TPage["items"];
  /** A resposta crua da página. A listagem de lançamentos precisa dela para o rodapé
   * de somatórios, que não é `items` nem paginação. */
  page: TPage | undefined;
  isLoading: boolean;
  error: string | null;
  nextCursor: string | null;
  pagination: {
    hasPreviousPage: boolean;
    hasNextPage: boolean;
    onPreviousPage: () => void;
    onNextPage: () => void;
  };
  /** Export respeita os filtros ativos, não a página visível (CLAUDE.md §6). */
  exportAs: (format: "xlsx" | "pdf") => Promise<void>;
  refresh: () => Promise<void>;
}

/** Padrão de listagem (spec 030, alvo 2): URL + query + paginação keyset + export num
 * hook só — o que as telas de contatos (019) e processos (027) repetiam linha a linha. */
export function useListPage<TFilters, TPage extends ListResponse<unknown>>({
  queryKey,
  filters,
  fetchPage,
  exportFile,
  resetDeps,
  limit = 20,
}: UseListPageOptions<TFilters, TPage>): UseListPageResult<TPage> {
  const queryClient = useQueryClient();
  const [cursorStack, setCursorStack] = React.useState<string[]>([]);
  const currentCursor = cursorStack[cursorStack.length - 1];

  const { data, isLoading, error } = useQuery({
    queryKey: [queryKey, filters, currentCursor],
    queryFn: () => fetchPage({ ...filters, cursor: currentCursor, limit }),
  });

  React.useEffect(() => {
    setCursorStack([]);
    // resetDeps é a lista de filtros que zera a paginação — a página declara uma por uma.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, resetDeps);

  return {
    items: data?.items ?? [],
    page: data,
    isLoading,
    error: error instanceof ApiError ? error.message : null,
    nextCursor: data?.next_cursor ?? null,
    pagination: {
      hasPreviousPage: cursorStack.length > 0,
      hasNextPage: data?.next_cursor != null,
      onPreviousPage: () => setCursorStack((stack) => stack.slice(0, -1)),
      onNextPage: () => {
        if (data?.next_cursor) {
          setCursorStack((stack) => [...stack, data.next_cursor as string]);
        }
      },
    },
    exportAs: (format) => exportFile?.(format, filters) ?? Promise.resolve(),
    refresh: () => queryClient.invalidateQueries({ queryKey: [queryKey] }),
  };
}

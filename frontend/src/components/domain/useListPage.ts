import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import type { ListResponse } from "@/components/domain/types";
import { ApiError } from "@/lib/errors";

export interface UseListPageOptions<TFilters, TItem> {
  /** Chave estável da query (ex.: "lawsuits-list") — o export e o refresh a reutilizam. */
  queryKey: string;
  /** Filtros ativos (já extraídos da URL pela página via `useFilters`). */
  filters: TFilters;
  fetchPage: (
    params: TFilters & { cursor: string | undefined; limit: number },
  ) => Promise<ListResponse<TItem>>;
  exportFile: (format: "xlsx" | "pdf", filters: TFilters) => Promise<void>;
  /** Quando qualquer um destes valores muda, a paginação volta para a primeira página. */
  resetDeps: readonly unknown[];
  limit?: number;
}

export interface UseListPageResult<TItem> {
  items: TItem[];
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
export function useListPage<TFilters, TItem>({
  queryKey,
  filters,
  fetchPage,
  exportFile,
  resetDeps,
  limit = 20,
}: UseListPageOptions<TFilters, TItem>): UseListPageResult<TItem> {
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
    exportAs: (format) => exportFile(format, filters),
    refresh: () => queryClient.invalidateQueries({ queryKey: [queryKey] }),
  };
}

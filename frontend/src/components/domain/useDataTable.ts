import * as React from "react";

import type { DataTableSort } from "@/components/domain/types";

export interface UseDataTableOptions {
  initialSort?: DataTableSort | null;
}

export interface UseDataTableResult {
  sort: DataTableSort | null;
  toggleSort: (field: string) => void;
  selectedIds: Set<string>;
  setSelectedIds: (ids: Set<string>) => void;
  toggleRow: (id: string) => void;
  clearSelection: () => void;
}

/** Estado de UI (ordenação + seleção) que toda tela de listagem precisa — quem busca os
 * dados é a feature (regra 1), este hook só evita repetir o mesmo useState em cada uma. */
export function useDataTable(options: UseDataTableOptions = {}): UseDataTableResult {
  const [sort, setSort] = React.useState<DataTableSort | null>(options.initialSort ?? null);
  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());

  const toggleSort = React.useCallback((field: string) => {
    setSort((current) => {
      if (!current || current.field !== field) {
        return { field, order: "asc" };
      }
      if (current.order === "asc") {
        return { field, order: "desc" };
      }
      return null;
    });
  }, []);

  const toggleRow = React.useCallback((id: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const clearSelection = React.useCallback(() => setSelectedIds(new Set()), []);

  return { sort, toggleSort, selectedIds, setSelectedIds, toggleRow, clearSelection };
}

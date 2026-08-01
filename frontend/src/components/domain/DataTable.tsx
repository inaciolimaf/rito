import { ArrowDown, ArrowUp, ArrowUpDown, Download } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/domain/EmptyState";
import type {
  DataTableColumn,
  DataTablePagination,
  DataTableSort,
} from "@/components/domain/types";
import { cn } from "@/lib/utils";

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  data: T[];
  getRowId: (row: T) => string;
  isLoading?: boolean;
  error?: string | null;
  emptyMessage?: string;
  sort?: DataTableSort | null;
  onSortChange?: (field: string) => void;
  selectedIds?: Set<string>;
  onSelectionChange?: (ids: Set<string>) => void;
  rowActions?: (row: T) => React.ReactNode;
  bulkActions?: { label: string; onClick: (selectedIds: string[]) => void }[];
  onExport?: (format: "xlsx" | "pdf") => void;
  pagination?: DataTablePagination;
}

/** Regra 1: nunca faz fetch sozinho — recebe dados e callbacks, quem busca é a feature. */
export function DataTable<T>({
  columns,
  data,
  getRowId,
  isLoading = false,
  error = null,
  emptyMessage = "Nada encontrado.",
  sort = null,
  onSortChange,
  selectedIds,
  onSelectionChange,
  rowActions,
  bulkActions,
  onExport,
  pagination,
}: DataTableProps<T>): JSX.Element {
  const selectable = selectedIds !== undefined && onSelectionChange !== undefined;
  const allIds = React.useMemo(() => data.map(getRowId), [data, getRowId]);
  const allSelected = selectable && allIds.length > 0 && allIds.every((id) => selectedIds.has(id));
  const someSelected = selectable && allIds.some((id) => selectedIds.has(id));

  function toggleAll(): void {
    if (!selectable) return;
    onSelectionChange(allSelected ? new Set() : new Set(allIds));
  }

  function toggleRow(id: string): void {
    if (!selectable) return;
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onSelectionChange(next);
  }

  if (error) {
    return (
      <EmptyState title="Não foi possível carregar os dados." description={error} role="alert" />
    );
  }

  if (!isLoading && data.length === 0) {
    return <EmptyState title={emptyMessage} />;
  }

  return (
    <div className="flex flex-col gap-3">
      {(onExport || (selectable && someSelected && bulkActions)) && (
        <div className="flex items-center justify-between gap-2">
          <div className="flex gap-2">
            {selectable &&
              someSelected &&
              bulkActions?.map((action) => (
                <Button
                  key={action.label}
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => action.onClick(Array.from(selectedIds))}
                >
                  {action.label}
                </Button>
              ))}
          </div>
          {onExport && (
            <div className="flex gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => onExport("xlsx")}>
                <Download className="mr-1 h-4 w-4" /> XLSX
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => onExport("pdf")}>
                <Download className="mr-1 h-4 w-4" /> PDF
              </Button>
            </div>
          )}
        </div>
      )}

      <div className="overflow-x-auto rounded border border-default">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-default bg-surface-muted">
              {selectable && (
                <th scope="col" className="w-10 px-3 py-2">
                  <Checkbox
                    checked={allSelected}
                    onCheckedChange={toggleAll}
                    aria-label="Selecionar todos"
                  />
                </th>
              )}
              {columns.map((column) => (
                <th
                  key={column.id}
                  scope="col"
                  className={cn("px-3 py-2 text-left font-medium text-muted", column.className)}
                >
                  {column.sortable && onSortChange ? (
                    <button
                      type="button"
                      className="flex items-center gap-1 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                      onClick={() => onSortChange(column.id)}
                    >
                      {column.header}
                      <SortIcon active={sort?.field === column.id} order={sort?.order} />
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              ))}
              {rowActions && (
                <th scope="col" className="px-3 py-2">
                  <span className="sr-only">Ações</span>
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 3 }).map((_, index) => (
                  <tr key={`skeleton-${index}`} className="border-b border-default last:border-0">
                    <td
                      colSpan={columns.length + (selectable ? 1 : 0) + (rowActions ? 1 : 0)}
                      className="px-3 py-3"
                    >
                      <div className="h-4 w-full animate-pulse rounded bg-surface-muted" />
                    </td>
                  </tr>
                ))
              : data.map((row) => {
                  const id = getRowId(row);
                  return (
                    <tr key={id} className="border-b border-default last:border-0">
                      {selectable && (
                        <td className="px-3 py-2">
                          <Checkbox
                            checked={selectedIds.has(id)}
                            onCheckedChange={() => toggleRow(id)}
                            aria-label={`Selecionar linha ${id}`}
                          />
                        </td>
                      )}
                      {columns.map((column) => (
                        <td
                          key={column.id}
                          className={cn("px-3 py-2 text-primary", column.className)}
                        >
                          {column.cell(row)}
                        </td>
                      ))}
                      {rowActions && <td className="px-3 py-2">{rowActions(row)}</td>}
                    </tr>
                  );
                })}
          </tbody>
        </table>
      </div>

      {pagination && (
        <div className="flex justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!pagination.hasPreviousPage}
            onClick={pagination.onPreviousPage}
          >
            Anterior
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!pagination.hasNextPage}
            onClick={pagination.onNextPage}
          >
            Próxima
          </Button>
        </div>
      )}
    </div>
  );
}

function SortIcon({ active, order }: { active?: boolean; order?: "asc" | "desc" }): JSX.Element {
  if (!active) return <ArrowUpDown className="h-3 w-3 opacity-50" />;
  return order === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />;
}

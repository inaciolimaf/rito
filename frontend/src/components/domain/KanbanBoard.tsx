import * as React from "react";

import { EmptyState } from "@/components/domain/EmptyState";

export interface KanbanColumnDef {
  id: string;
  label: string;
  total: number;
}

export interface KanbanBoardProps<T> {
  columns: KanbanColumnDef[];
  itemsByColumn: Record<string, T[]>;
  getItemId: (item: T) => string;
  renderCard: (item: T) => React.ReactNode;
  onMove: (itemId: string, fromColumnId: string, toColumnId: string) => void;
  onLoadMore?: (columnId: string) => void;
  hasMoreByColumn?: Record<string, boolean>;
  loadingColumnId?: string | null;
  /** Regra do refactor 060 (SOLID): o componente não sabe o que é um "processo" —
   * quem chama decide os textos de estado vazio. */
  emptyColumnMessage?: string;
  emptyBoardTitle?: string;
  emptyBoardDescription?: string;
}

/** `KanbanBoard<T>` genérico (spec 051 §6) — não conhece processo; recebe colunas,
 * itens por coluna, `onMove` e um render de card. Drag & drop nativo do HTML5 (mesmo
 * padrão sem dependência nova de `InboxSettingsForm`, spec 036), com persistência
 * OTIMISTA por conta do chamador (regra 4: o item já muda de coluna na hora — se
 * `onMove` reverter o estado do pai, o card volta sozinho no próximo render). Volume:
 * cada coluna é limitada por `limit_per_column`/paginação por scroll (regra 7) — o
 * DOM nunca cresce ilimitado, mesmo sem uma lib de virtualização por janela. */
export function KanbanBoard<T>({
  columns,
  itemsByColumn,
  getItemId,
  renderCard,
  onMove,
  onLoadMore,
  hasMoreByColumn,
  loadingColumnId,
  emptyColumnMessage = "Nenhum item",
  emptyBoardTitle = "Nenhuma coluna configurada",
  emptyBoardDescription = "Configure as colunas do board.",
}: KanbanBoardProps<T>): JSX.Element {
  const dragRef = React.useRef<{ itemId: string; fromColumnId: string } | null>(null);
  const [dragOverColumnId, setDragOverColumnId] = React.useState<string | null>(null);

  function handleDrop(toColumnId: string): void {
    const dragged = dragRef.current;
    dragRef.current = null;
    setDragOverColumnId(null);
    if (!dragged || dragged.fromColumnId === toColumnId) {
      return;
    }
    onMove(dragged.itemId, dragged.fromColumnId, toColumnId);
  }

  return (
    <div className="flex gap-4 overflow-x-auto pb-4" role="list" aria-label="Board Kanban">
      {columns.map((column) => {
        const items = itemsByColumn[column.id] ?? [];
        return (
          <div
            key={column.id}
            role="listitem"
            aria-label={column.label}
            data-testid={`kanban-column-${column.id}`}
            onDragOver={(event) => {
              event.preventDefault();
              setDragOverColumnId(column.id);
            }}
            onDragLeave={() =>
              setDragOverColumnId((current) => (current === column.id ? null : current))
            }
            onDrop={() => handleDrop(column.id)}
            className={`flex w-72 shrink-0 flex-col rounded border border-default bg-surface-muted/40 ${
              dragOverColumnId === column.id ? "ring-2 ring-accent" : ""
            }`}
          >
            <div className="flex items-center justify-between border-b border-default px-3 py-2">
              <h3 className="text-sm font-semibold text-primary">{column.label}</h3>
              <span className="text-xs text-muted">{column.total}</span>
            </div>
            <div className="flex flex-col gap-2 p-2">
              {items.length === 0 ? (
                <p className="px-1 py-4 text-center text-xs text-muted">{emptyColumnMessage}</p>
              ) : (
                items.map((item) => {
                  const itemId = getItemId(item);
                  return (
                    <div
                      key={itemId}
                      draggable
                      data-testid={`kanban-card-${itemId}`}
                      onDragStart={() => {
                        dragRef.current = { itemId, fromColumnId: column.id };
                      }}
                      onDragEnd={() => {
                        dragRef.current = null;
                        setDragOverColumnId(null);
                      }}
                      className="cursor-grab rounded border border-default bg-surface p-2 shadow-sm"
                    >
                      {renderCard(item)}
                    </div>
                  );
                })
              )}
              {hasMoreByColumn?.[column.id] && (
                <button
                  type="button"
                  className="rounded border border-default py-1 text-xs text-accent disabled:opacity-50"
                  disabled={loadingColumnId === column.id}
                  onClick={() => onLoadMore?.(column.id)}
                >
                  {loadingColumnId === column.id ? "Carregando…" : "Carregar mais"}
                </button>
              )}
            </div>
          </div>
        );
      })}
      {columns.length === 0 && (
        <EmptyState title={emptyBoardTitle} description={emptyBoardDescription} />
      )}
    </div>
  );
}

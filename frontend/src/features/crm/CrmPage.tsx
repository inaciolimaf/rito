import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { FilterBar } from "@/components/domain/FilterBar";
import { KanbanBoard, type KanbanColumnDef } from "@/components/domain/KanbanBoard";
import type { FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { Button } from "@/components/ui/button";
import {
  bulkMoveLawsuitStage,
  getBoard,
  getBoardColumn,
  moveLawsuitStage,
  type Board,
  type BoardCard,
  type BoardFilters,
} from "@/features/crm/api";
import { LawsuitCard } from "@/features/crm/LawsuitCard";
import { listStages } from "@/features/stages/api";

const FILTER_FIELDS: FilterFieldDef[] = [
  { key: "q", label: "Buscar", type: "text" },
  { key: "archived", label: "Arquivados", type: "boolean" },
];

/** Tela do CRM — board Kanban (spec 051). Filtros são os mesmos de `/lawsuits`
 * (regra 8: o backend aceita o `LawsuitFiltersQuery` inteiro) — só um subconjunto
 * prático vira controle nesta tela. */
export function CrmPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { values } = useFilters(FILTER_FIELDS);
  const q = typeof values.q === "string" ? values.q : undefined;
  const archived = values.archived === undefined ? undefined : values.archived === "true";
  const filters: BoardFilters = { q, archived };
  const boardKey = ["crm", "board", filters] as const;

  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [bulkTargetStage, setBulkTargetStage] = React.useState("");
  const [confirmingBulkMove, setConfirmingBulkMove] = React.useState(false);
  const [extraColumnItems, setExtraColumnItems] = React.useState<Record<string, BoardCard[]>>({});
  const [nextCursorByColumn, setNextCursorByColumn] = React.useState<Record<string, string | null>>(
    {},
  );
  const [loadingColumnId, setLoadingColumnId] = React.useState<string | null>(null);

  const { data: board, isLoading } = useQuery({
    queryKey: boardKey,
    queryFn: () => getBoard(filters),
  });
  const { data: stagesPage } = useQuery({
    queryKey: ["stages", "all-for-crm"],
    queryFn: () => listStages({}),
  });

  React.useEffect(() => {
    setExtraColumnItems({});
    setNextCursorByColumn({});
  }, [board]);

  const firstStageByStep = React.useMemo(() => {
    const map = new Map<number, string>();
    for (const stage of stagesPage?.items ?? []) {
      if (!map.has(stage.step_id)) map.set(stage.step_id, stage.id);
    }
    return map;
  }, [stagesPage]);

  const invalidateBoard = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: ["crm", "board"] }).then(() => undefined);

  const move = useMutation({
    mutationFn: ({ lawsuitId, stageId }: { lawsuitId: string; stageId: string }) =>
      moveLawsuitStage(lawsuitId, stageId),
    // Regra 4: reverte buscando o board de novo do servidor se a API falhar.
    onError: invalidateBoard,
    onSuccess: invalidateBoard,
  });

  function handleMove(itemId: string, fromColumnId: string, toColumnId: string): void {
    const toStepId = Number(toColumnId);
    const targetStageId = firstStageByStep.get(toStepId); // regra 3
    if (!targetStageId) return;

    // Otimista: move o card na hora no cache local (regra 4); onError/onSuccess
    // acima confirmam com um fetch de verdade do servidor.
    queryClient.setQueryData<Board>(boardKey, (current) => {
      if (!current) return current;
      let moved: BoardCard | undefined;
      const columns = current.columns.map((column) => {
        if (String(column.step_id) !== fromColumnId) return column;
        const remaining = column.items.filter((item) => {
          if (item.id === itemId) {
            moved = item;
            return false;
          }
          return true;
        });
        return { ...column, items: remaining, total: column.total - (moved ? 1 : 0) };
      });
      if (!moved) return current;
      return {
        ...current,
        columns: columns.map((column) =>
          String(column.step_id) === toColumnId
            ? { ...column, items: [moved as BoardCard, ...column.items], total: column.total + 1 }
            : column,
        ),
      };
    });
    move.mutate({ lawsuitId: itemId, stageId: targetStageId });
  }

  async function handleLoadMore(columnId: string): Promise<void> {
    setLoadingColumnId(columnId);
    try {
      const cursor = nextCursorByColumn[columnId] ?? undefined;
      const page = await getBoardColumn(Number(columnId), { ...filters, cursor, limit: 50 });
      setExtraColumnItems((current) => ({
        ...current,
        [columnId]: [...(current[columnId] ?? []), ...page.items],
      }));
      setNextCursorByColumn((current) => ({ ...current, [columnId]: page.next_cursor }));
    } finally {
      setLoadingColumnId(null);
    }
  }

  function toggleSelected(id: string): void {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const bulkMove = useMutation({
    mutationFn: () => bulkMoveLawsuitStage([...selected], bulkTargetStage),
    onSuccess: async () => {
      setSelected(new Set());
      setBulkTargetStage("");
      setConfirmingBulkMove(false);
      await invalidateBoard();
    },
  });
  const bulkTargetStageName = stagesPage?.items.find((stage) => stage.id === bulkTargetStage);

  if (isLoading || !board) {
    return <p className="p-6 text-sm text-muted">Carregando board…</p>;
  }

  const columns: KanbanColumnDef[] = board.columns.map((column) => ({
    id: String(column.step_id),
    label: column.step_name,
    total: column.total,
  }));

  const itemsByColumn: Record<string, BoardCard[]> = {};
  const hasMoreByColumn: Record<string, boolean> = {};
  for (const column of board.columns) {
    const columnId = String(column.step_id);
    itemsByColumn[columnId] = [...column.items, ...(extraColumnItems[columnId] ?? [])];
    hasMoreByColumn[columnId] = Boolean(nextCursorByColumn[columnId]);
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">CRM</h1>
        {selected.size > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted">{selected.size} selecionado(s)</span>
            <select
              aria-label="Mover selecionados para"
              className="h-9 rounded border border-default bg-surface px-2 text-sm"
              value={bulkTargetStage}
              onChange={(event) => setBulkTargetStage(event.target.value)}
            >
              <option value="">Mover para…</option>
              {(stagesPage?.items ?? []).map((stage) => (
                <option key={stage.id} value={stage.id}>
                  {stage.step_name} — {stage.name}
                </option>
              ))}
            </select>
            <Button
              size="sm"
              disabled={!bulkTargetStage || bulkMove.isPending}
              onClick={() => setConfirmingBulkMove(true)}
            >
              Aplicar
            </Button>
          </div>
        )}
      </div>

      {board.suggest_refine_filters && (
        <p
          role="status"
          className="rounded border border-warning bg-warning/10 p-2 text-sm text-warning"
        >
          Mais de 2.000 processos no board — refine os filtros para uma visão mais rápida.
        </p>
      )}

      <FilterBar fields={FILTER_FIELDS} />

      <KanbanBoard
        columns={columns}
        itemsByColumn={itemsByColumn}
        getItemId={(item) => item.id}
        onMove={handleMove}
        onLoadMore={(columnId) => void handleLoadMore(columnId)}
        hasMoreByColumn={hasMoreByColumn}
        loadingColumnId={loadingColumnId}
        renderCard={(item) => (
          <div>
            <label className="mb-1 flex items-center gap-1 text-xs text-muted">
              <input
                type="checkbox"
                checked={selected.has(item.id)}
                onChange={() => toggleSelected(item.id)}
              />
              selecionar
            </label>
            <LawsuitCard card={item} />
          </div>
        )}
      />

      <ConfirmDialog
        open={confirmingBulkMove}
        onOpenChange={setConfirmingBulkMove}
        title="Mover processos selecionados?"
        description={`${selected.size} processo(s) vão pra "${bulkTargetStageName?.step_name ?? ""} — ${bulkTargetStageName?.name ?? ""}".`}
        confirmLabel="Mover"
        onConfirm={() => bulkMove.mutate()}
      />
    </div>
  );
}

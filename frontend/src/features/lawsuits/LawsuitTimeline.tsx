import { useInfiniteQuery } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { EmptyState } from "@/components/domain/EmptyState";
import { Button } from "@/components/ui/button";
import {
  deleteMovement,
  getTimeline,
  type TimelineItem as TimelineItemData,
  type TimelineKind,
} from "@/features/lawsuits/api";
import { TimelineItem } from "@/features/lawsuits/TimelineItem";

export interface LawsuitTimelineProps {
  lawsuitId: string;
  kinds: TimelineKind[];
  onEditMovement: (item: TimelineItemData) => void;
}

/** Timeline unificada do processo (spec 026): paginação por cursor ("carregar mais"),
 * estado vazio distinto para "nenhum tipo marcado" (regra 2) e ações só em itens
 * `movement_manual` (regra 3: tribunal é imutável pela UI). */
export function LawsuitTimeline({
  lawsuitId,
  kinds,
  onEditMovement,
}: LawsuitTimelineProps): JSX.Element {
  const [pendingDelete, setPendingDelete] = React.useState<TimelineItemData | null>(null);

  const timelineQuery = useInfiniteQuery({
    queryKey: ["lawsuit-timeline", lawsuitId, kinds.join(",")],
    queryFn: ({ pageParam }) =>
      getTimeline(lawsuitId, { kinds, cursor: pageParam ?? undefined, limit: 20 }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: kinds.length > 0,
  });

  async function handleConfirmDelete(): Promise<void> {
    if (!pendingDelete) return;
    await deleteMovement(lawsuitId, pendingDelete.id);
    setPendingDelete(null);
    await timelineQuery.refetch();
  }

  if (kinds.length === 0) {
    return (
      <EmptyState
        title="Nenhum tipo de evento selecionado"
        description="Marque ao menos um tipo acima para ver a timeline do processo."
      />
    );
  }

  const items = timelineQuery.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="space-y-3">
      {timelineQuery.isLoading ? (
        <p className="text-sm text-muted">Carregando timeline…</p>
      ) : items.length === 0 ? (
        <EmptyState
          title="Nada por aqui ainda"
          description="Nenhum evento dos tipos selecionados neste processo."
        />
      ) : (
        <ul className="space-y-2" aria-label="Timeline do processo">
          {items.map((item) => (
            <TimelineItem
              key={`${item.kind}-${item.id}`}
              item={item}
              onEdit={item.kind === "movement_manual" ? onEditMovement : undefined}
              onDelete={item.kind === "movement_manual" ? setPendingDelete : undefined}
            />
          ))}
        </ul>
      )}

      {timelineQuery.hasNextPage && (
        <Button
          variant="outline"
          onClick={() => void timelineQuery.fetchNextPage()}
          disabled={timelineQuery.isFetchingNextPage}
        >
          Carregar mais
        </Button>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir movimentação?"
        description="A movimentação manual será removida da timeline do processo."
        confirmLabel="Excluir"
        destructive
        onConfirm={() => void handleConfirmDelete()}
      />
    </div>
  );
}

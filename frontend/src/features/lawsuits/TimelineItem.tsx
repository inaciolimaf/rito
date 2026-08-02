import type { TimelineItem as TimelineItemData, TimelineKind } from "@/features/lawsuits/api";
import { cn } from "@/lib/utils";

export const TIMELINE_KIND_META: Record<TimelineKind, { label: string; badgeClass: string }> = {
  task: { label: "Tarefa", badgeClass: "bg-accent/10 text-accent" },
  movement_auto: { label: "Andamento", badgeClass: "bg-surface-muted text-primary" },
  movement_manual: { label: "Movimentação manual", badgeClass: "bg-surface-muted text-muted" },
  publication: { label: "Publicação", badgeClass: "bg-accent/10 text-accent" },
  transaction: { label: "Financeiro", badgeClass: "bg-surface-muted text-primary" },
};

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export interface TimelineItemProps {
  item: TimelineItemData;
  /** Só movimentações manuais podem ser editadas/excluídas (regras 3 e 4) — a página
   * decide QUANDO mostrar as ações; o item só renderiza os botões. */
  onEdit?: (item: TimelineItemData) => void;
  onDelete?: (item: TimelineItemData) => void;
}

/** Item da timeline com variante por tipo (spec 026 §6): selo, título, data/hora pt-BR,
 * resumo e origem (ator humano ou cabeçalho do tribunal). */
export function TimelineItem({ item, onEdit, onDelete }: TimelineItemProps): JSX.Element {
  const meta = TIMELINE_KIND_META[item.kind];
  return (
    <li className="flex gap-3 rounded border border-default bg-surface p-3">
      <span
        className={cn("h-fit shrink-0 rounded px-2 py-0.5 text-xs font-medium", meta.badgeClass)}
      >
        {meta.label}
      </span>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-baseline justify-between gap-2">
          <p className="font-medium text-primary">{item.title}</p>
          <time className="shrink-0 text-xs text-muted">
            {dateTimeFormatter.format(new Date(item.occurred_at))}
          </time>
        </div>
        {item.summary && <p className="text-sm text-muted">{item.summary}</p>}
        {(item.actor || item.metadata.header) && (
          <p className="text-xs text-muted">{item.actor ?? item.metadata.header}</p>
        )}
      </div>
      {(onEdit || onDelete) && (
        <div className="flex shrink-0 flex-col gap-1">
          {onEdit && (
            <button
              type="button"
              className="text-xs text-accent underline"
              onClick={() => onEdit(item)}
            >
              Editar
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              className="text-xs text-danger underline"
              onClick={() => onDelete(item)}
            >
              Excluir
            </button>
          )}
        </div>
      )}
    </li>
  );
}

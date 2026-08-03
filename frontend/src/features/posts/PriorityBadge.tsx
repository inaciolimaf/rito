import { Star } from "lucide-react";

export interface PriorityBadgeProps {
  isImportant?: boolean;
  isUrgent?: boolean;
  isPrivate?: boolean;
}

/** Badges de prioridade da tarefa (spec 033 §6): urgente = "!", importante = ★,
 * privada = "Privada". Combináveis (regra 10) — uma tarefa pode ter os três. */
export function PriorityBadge({
  isImportant = false,
  isUrgent = false,
  isPrivate = false,
}: PriorityBadgeProps): JSX.Element | null {
  if (!isImportant && !isUrgent && !isPrivate) return null;
  return (
    <span className="inline-flex items-center gap-1" aria-label="Prioridade">
      {isUrgent && (
        <span
          aria-label="Urgente"
          title="Urgente"
          className="inline-flex h-4 w-4 items-center justify-center rounded-full bg-danger text-xs font-bold text-danger-foreground"
        >
          !
        </span>
      )}
      {isImportant && (
        <Star aria-label="Importante" className="h-3.5 w-3.5 fill-warning text-warning" />
      )}
      {isPrivate && (
        <span className="rounded bg-surface-muted px-1.5 text-xs text-muted">Privada</span>
      )}
    </span>
  );
}

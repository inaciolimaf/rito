import { TIMELINE_KIND_META } from "@/features/lawsuits/TimelineItem";
import type { TimelineKind } from "@/features/lawsuits/api";

export const ALL_TIMELINE_KINDS: TimelineKind[] = [
  "task",
  "movement_auto",
  "movement_manual",
  "publication",
  "transaction",
];

export interface TimelineFiltersProps {
  kinds: TimelineKind[];
  onChange: (kinds: TimelineKind[]) => void;
}

/** Toggles por tipo de evento (spec 026 §6) — combináveis (regra 2); a seleção é
 * persistida por usuário (regra 7) pelo `useTimelineKinds`, não por este componente. */
export function TimelineFilters({ kinds, onChange }: TimelineFiltersProps): JSX.Element {
  function toggle(kind: TimelineKind): void {
    onChange(kinds.includes(kind) ? kinds.filter((k) => k !== kind) : [...kinds, kind]);
  }

  return (
    <div className="flex flex-wrap gap-3" role="group" aria-label="Tipos de evento">
      {ALL_TIMELINE_KINDS.map((kind) => (
        <label key={kind} className="flex items-center gap-1 text-sm text-primary">
          <input
            type="checkbox"
            checked={kinds.includes(kind)}
            onChange={() => toggle(kind)}
            aria-label={`Mostrar ${TIMELINE_KIND_META[kind].label}`}
          />
          {TIMELINE_KIND_META[kind].label}
        </label>
      ))}
    </div>
  );
}

import type { ScheduleEvent } from "@/features/schedule/api";
import {
  WEEKDAY_LABELS,
  formatIsoDay,
  groupByDay,
  monthGridDays,
} from "@/features/schedule/calendar";
import { EventChip } from "@/features/schedule/EventChip";

const MAX_VISIBLE = 3;

export interface MonthViewProps {
  anchor: Date;
  events: ScheduleEvent[];
  onDayClick: (day: Date) => void;
  onEventClick: (event: ScheduleEvent) => void;
}

/** Visão mês (spec 037 §6): grade de 42 células; regra 7 — clicar no dia abre o
 * formulário com a data pré-preenchida (o clique no chip NÃO dispara, via stopPropagation). */
export function MonthView({
  anchor,
  events,
  onDayClick,
  onEventClick,
}: MonthViewProps): JSX.Element {
  const days = monthGridDays(anchor);
  const byDay = groupByDay(events);
  const today = formatIsoDay(new Date());

  return (
    <div data-testid="month-view" className="rounded border border-default bg-surface">
      <div className="grid grid-cols-7 border-b border-default">
        {WEEKDAY_LABELS.map((label) => (
          <div key={label} className="px-2 py-1 text-center text-xs font-medium text-muted">
            {label}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {days.map((day) => {
          const iso = formatIsoDay(day);
          const dayEvents = byDay.get(iso) ?? [];
          const outside = day.getMonth() !== anchor.getMonth();
          return (
            // div, não <button>: os chips dos eventos são botões e button dentro de
            // button é HTML inválido — o clique no centro da célula cairia no chip
            // (flake da jornada 6/25).
            <div
              key={iso}
              role="button"
              tabIndex={0}
              data-testid={`day-cell-${iso}`}
              onClick={() => onDayClick(day)}
              onKeyDown={(event) => {
                if (event.key === "Enter") onDayClick(day);
              }}
              className={`flex min-h-24 cursor-pointer flex-col gap-0.5 border-b border-r border-default p-1 text-left align-top hover:bg-surface-muted ${
                outside ? "bg-surface-muted text-muted" : ""
              }`}
            >
              <span
                className={`self-start rounded px-1 text-xs ${
                  iso === today ? "bg-accent font-bold text-accent-foreground" : ""
                }`}
              >
                {day.getDate()}
              </span>
              {dayEvents.slice(0, MAX_VISIBLE).map((event) => (
                <EventChip key={event.post_id} event={event} onClick={onEventClick} />
              ))}
              {dayEvents.length > MAX_VISIBLE && (
                <span className="px-1 text-xs text-muted">
                  +{dayEvents.length - MAX_VISIBLE} mais
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

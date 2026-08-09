import type { ScheduleEvent } from "@/features/schedule/api";
import {
  WEEKDAY_LABELS,
  addDays,
  formatIsoDay,
  groupByDay,
  startOfWeek,
} from "@/features/schedule/calendar";
import { EventChip } from "@/features/schedule/EventChip";

export interface WeekViewProps {
  anchor: Date;
  events: ScheduleEvent[];
  onDayClick: (day: Date) => void;
  onEventClick: (event: ScheduleEvent) => void;
}

/** Visão semana (spec 037 §6): 7 colunas, eventos ordenados (dia inteiro, depois hora). */
export function WeekView({ anchor, events, onDayClick, onEventClick }: WeekViewProps): JSX.Element {
  const first = startOfWeek(anchor);
  const days = Array.from({ length: 7 }, (_, index) => addDays(first, index));
  const byDay = groupByDay(events);
  const today = formatIsoDay(new Date());

  return (
    <div
      data-testid="week-view"
      className="grid grid-cols-7 rounded border border-default bg-surface"
    >
      {days.map((day) => {
        const iso = formatIsoDay(day);
        const dayEvents = byDay.get(iso) ?? [];
        return (
          // div, não <button> (mesmo motivo do MonthView): chips são botões.
          <div
            key={iso}
            role="button"
            tabIndex={0}
            data-testid={`day-cell-${iso}`}
            onClick={() => onDayClick(day)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onDayClick(day);
            }}
            className="flex min-h-40 cursor-pointer flex-col gap-0.5 border-r border-default p-1 text-left last:border-r-0 hover:bg-surface-muted"
          >
            <span
              className={`self-start rounded px-1 text-xs font-medium ${
                iso === today ? "bg-accent text-accent-foreground" : "text-muted"
              }`}
            >
              {WEEKDAY_LABELS[day.getDay()]} {day.getDate()}
            </span>
            {dayEvents.map((event) => (
              <EventChip key={event.post_id} event={event} onClick={onEventClick} />
            ))}
          </div>
        );
      })}
    </div>
  );
}

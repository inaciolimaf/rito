import type { ScheduleEvent } from "@/features/schedule/api";
import {
  STATUS_DOT_CLASSES,
  STATUS_LABELS,
  formatIsoDay,
  formatTime,
  groupByDay,
} from "@/features/schedule/calendar";

export interface DayViewProps {
  anchor: Date;
  events: ScheduleEvent[];
  onEventClick: (event: ScheduleEvent) => void;
}

/** Visão dia (spec 037 §6): lista detalhada do dia — hora, tipo, responsáveis,
 * local e status por extenso (regra 3: o rótulo acompanha a cor). */
export function DayView({ anchor, events, onEventClick }: DayViewProps): JSX.Element {
  const dayEvents = groupByDay(events).get(formatIsoDay(anchor)) ?? [];

  return (
    <div data-testid="day-view" className="rounded border border-default bg-surface p-3">
      {dayEvents.length === 0 ? (
        <p className="text-sm text-muted">Nenhum compromisso neste dia.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {dayEvents.map((event) => (
            <li key={event.post_id}>
              <button
                type="button"
                data-testid="schedule-event"
                data-status={event.status}
                onClick={() => onEventClick(event)}
                className="flex w-full items-center gap-3 rounded border border-default p-2 text-left hover:bg-surface-muted"
              >
                <span
                  aria-hidden
                  className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT_CLASSES[event.status]}`}
                />
                <span className="w-14 shrink-0 text-sm font-medium">
                  {event.all_day ? "Dia todo" : formatTime(event.scheduled_time)}
                </span>
                <span className="flex-1">
                  <span className="block text-sm font-medium">{event.task_type_name}</span>
                  <span className="block text-xs text-muted">
                    {event.assignee_names.join(", ")}
                    {event.location ? ` · ${event.location}` : ""}
                  </span>
                </span>
                <span className="text-xs text-muted">{STATUS_LABELS[event.status]}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

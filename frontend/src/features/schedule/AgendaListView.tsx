import { EmptyState } from "@/components/domain/EmptyState";
import type { ScheduleEvent } from "@/features/schedule/api";
import {
  WEEKDAY_LABELS,
  formatBrDay,
  formatTime,
  groupByDay,
  parseIsoDay,
  STATUS_DOT_CLASSES,
} from "@/features/schedule/calendar";

export interface AgendaListViewProps {
  events: ScheduleEvent[];
  onEventClick: (event: ScheduleEvent) => void;
}

/** Visão lista (spec 037 §6): os próximos 30 dias em ordem cronológica, agrupados
 * por dia — a visão de "o que vem aí" da agenda. */
export function AgendaListView({ events, onEventClick }: AgendaListViewProps): JSX.Element {
  const byDay = groupByDay(events);
  const days = [...byDay.keys()].sort();

  if (days.length === 0) {
    return (
      <div data-testid="agenda-view">
        <EmptyState
          title="Nenhum compromisso no período"
          description="Ajuste os filtros ou crie uma tarefa com a opção Mostrar na agenda."
        />
      </div>
    );
  }

  return (
    <div data-testid="agenda-view" className="flex flex-col gap-3">
      {days.map((iso) => {
        const day = parseIsoDay(iso);
        return (
          <section key={iso} className="rounded border border-default bg-surface">
            <header className="border-b border-default px-3 py-1.5 text-sm font-medium">
              {WEEKDAY_LABELS[day.getDay()]} · {formatBrDay(day)}
            </header>
            <ul className="flex flex-col divide-y divide-default">
              {byDay.get(iso)?.map((event) => (
                <li key={event.post_id}>
                  <button
                    type="button"
                    data-testid="schedule-event"
                    data-status={event.status}
                    onClick={() => onEventClick(event)}
                    className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-surface-muted"
                  >
                    <span
                      aria-hidden
                      className={`h-2.5 w-2.5 shrink-0 rounded-full ${STATUS_DOT_CLASSES[event.status]}`}
                    />
                    <span className="w-14 shrink-0 text-sm">
                      {event.all_day ? "Dia todo" : formatTime(event.scheduled_time)}
                    </span>
                    <span className="flex-1 text-sm">{event.task_type_name}</span>
                    <span className="text-xs text-muted">{event.assignee_names.join(", ")}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}

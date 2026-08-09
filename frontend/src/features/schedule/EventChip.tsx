import type { ScheduleEvent } from "@/features/schedule/api";
import { STATUS_CHIP_CLASSES, formatTime } from "@/features/schedule/calendar";

export interface EventChipProps {
  event: ScheduleEvent;
  onClick: (event: ScheduleEvent) => void;
}

/** O chip do evento em qualquer visão — data-status é o contrato das cores
 * (regra 3) para testes/E2E. */
export function EventChip({ event, onClick }: EventChipProps): JSX.Element {
  return (
    <button
      type="button"
      data-testid="schedule-event"
      data-status={event.status}
      onClick={(clickEvent) => {
        clickEvent.stopPropagation();
        onClick(event);
      }}
      title={`${event.task_type_name} — ${event.assignee_names.join(", ")}`}
      className={`block w-full truncate rounded border-l-4 px-1.5 py-0.5 text-left text-xs ${STATUS_CHIP_CLASSES[event.status]}`}
    >
      {!event.all_day && event.scheduled_time && (
        <span className="mr-1 font-medium">{formatTime(event.scheduled_time)}</span>
      )}
      {event.task_type_name}
    </button>
  );
}

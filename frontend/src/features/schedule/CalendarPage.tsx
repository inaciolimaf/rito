import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { FilterBar } from "@/components/domain/FilterBar";
import type { FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { Button } from "@/components/ui/button";
import { NewTaskModal } from "@/features/posts/NewTaskModal";
import type { ScheduleDateField, ScheduleEvent } from "@/features/schedule/api";
import { listSchedule } from "@/features/schedule/api";
import {
  VIEW_LABELS,
  formatBrDay,
  formatIsoDay,
  parseIsoDay,
  shiftAnchor,
  viewRange,
  type ScheduleView,
} from "@/features/schedule/calendar";
import { AgendaListView } from "@/features/schedule/AgendaListView";
import { DayView } from "@/features/schedule/DayView";
import { ICalSettingsCard } from "@/features/schedule/ICalSettingsCard";
import { MonthView } from "@/features/schedule/MonthView";
import { WeekView } from "@/features/schedule/WeekView";
import { listUsers } from "@/features/users/api";

const VIEW_ORDER: ScheduleView[] = ["month", "week", "day", "agenda"];

function buildFilterFields(userOptions: { value: string; label: string }[]): FilterFieldDef[] {
  return [
    { key: "user_id", label: "Responsável", type: "select", options: userOptions },
    {
      key: "date_field",
      label: "Eixo da data",
      type: "select",
      options: [
        { value: "scheduled", label: "Compromisso" },
        { value: "deadline", label: "Prazo fatal" },
      ],
    },
    {
      key: "show_completed",
      label: "Concluídas",
      type: "select",
      options: [
        { value: "true", label: "Mostrar" },
        { value: "false", label: "Ocultar" },
      ],
    },
  ];
}

/** Agenda (spec 037 §6, rota /schedules): 4 visões sobre o mesmo intervalo, filtros
 * na URL (responsável, eixo compromisso × prazo fatal, concluídas), clique no dia
 * cria tarefa com a data preenchida (regra 7) e clique no evento abre a tarefa. */
export function CalendarPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [view, setView] = React.useState<ScheduleView>("month");
  const [anchor, setAnchor] = React.useState<Date>(() => new Date());
  const [newTaskDate, setNewTaskDate] = React.useState<string | null>(null);

  const { data: usersPage } = useQuery({
    queryKey: ["users", "schedule-filter"],
    queryFn: () => listUsers({ limit: 100 }),
  });
  const userOptions = (usersPage?.items ?? []).map((user) => ({
    value: user.id,
    label: user.name,
  }));
  const fields = React.useMemo(() => buildFilterFields(userOptions), [userOptions]);
  const { values } = useFilters(fields);

  const dateField = (
    values.date_field === "deadline" ? "deadline" : "scheduled"
  ) as ScheduleDateField;
  const showCompleted = values.show_completed !== "false";
  const userId = typeof values.user_id === "string" ? values.user_id : undefined;

  const range = viewRange(view, anchor);
  const { data: events = [], isLoading } = useQuery({
    queryKey: ["schedule", range.from, range.to, userId, dateField, showCompleted],
    queryFn: () =>
      listSchedule({
        from: range.from,
        to: range.to,
        userId,
        dateField,
        showCompleted,
      }),
  });

  function openEvent(event: ScheduleEvent): void {
    navigate(`/posts/${event.post_id}`);
  }

  function handleDayClick(day: Date): void {
    setNewTaskDate(formatIsoDay(day));
  }

  function closeNewTask(): void {
    setNewTaskDate(null);
    // A tarefa nova pode entrar na visão atual — NewTaskModal invalida "posts",
    // a agenda tem chave própria.
    void queryClient.invalidateQueries({ queryKey: ["schedule"] });
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-lg font-semibold">Agenda</h1>
        <div className="flex items-center gap-1 rounded border border-default p-0.5">
          {VIEW_ORDER.map((option) => (
            <button
              key={option}
              type="button"
              data-testid={`view-${option}`}
              onClick={() => setView(option)}
              className={`rounded px-3 py-1 text-sm ${
                view === option
                  ? "bg-accent text-accent-foreground"
                  : "text-muted hover:bg-surface-muted"
              }`}
            >
              {VIEW_LABELS[option]}
            </button>
          ))}
        </div>
      </div>

      <FilterBar fields={fields} />

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setAnchor((current) => shiftAnchor(view, current, -1))}
        >
          ← Anterior
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setAnchor(new Date())}>
          Hoje
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setAnchor((current) => shiftAnchor(view, current, 1))}
        >
          Próximo →
        </Button>
        <span data-testid="anchor-label" className="ml-2 text-sm text-muted">
          {formatBrDay(parseIsoDay(range.from))}
          {range.from !== range.to && ` — ${formatBrDay(parseIsoDay(range.to))}`}
        </span>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted">Carregando…</p>
      ) : view === "month" ? (
        <MonthView
          anchor={anchor}
          events={events}
          onDayClick={handleDayClick}
          onEventClick={openEvent}
        />
      ) : view === "week" ? (
        <WeekView
          anchor={anchor}
          events={events}
          onDayClick={handleDayClick}
          onEventClick={openEvent}
        />
      ) : view === "day" ? (
        <DayView anchor={anchor} events={events} onEventClick={openEvent} />
      ) : (
        <AgendaListView events={events} onEventClick={openEvent} />
      )}

      <ICalSettingsCard />

      <NewTaskModal
        open={newTaskDate !== null}
        onOpenChange={(open) => {
          if (!open) closeNewTask();
        }}
        initialDate={newTaskDate}
      />
    </div>
  );
}

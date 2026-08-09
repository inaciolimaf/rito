import type { ScheduleEvent, ScheduleStatus } from "@/features/schedule/api";

export type ScheduleView = "month" | "week" | "day" | "agenda";

export const VIEW_LABELS: Record<ScheduleView, string> = {
  month: "Mês",
  week: "Semana",
  day: "Dia",
  agenda: "Agenda",
};

/** Regra 3 — cores por status. O atributo data-status nos chips é o contrato
 * estável para testes e E2E; estas classes são a expressão visual dele (sempre
 * tokens semânticos, nunca cor crua — spec 006 regra 7). */
export const STATUS_CHIP_CLASSES: Record<ScheduleStatus, string> = {
  PENDENTE: "border-l-default bg-surface-muted text-primary",
  CONCLUIDA: "border-l-success bg-success/15 text-success",
  ATRASADA: "border-l-danger bg-danger/15 text-danger",
};

export const STATUS_DOT_CLASSES: Record<ScheduleStatus, string> = {
  PENDENTE: "bg-muted",
  CONCLUIDA: "bg-success",
  ATRASADA: "bg-danger",
};

export const STATUS_LABELS: Record<ScheduleStatus, string> = {
  PENDENTE: "Pendente",
  CONCLUIDA: "Concluída",
  ATRASADA: "Atrasada",
};

export const WEEKDAY_LABELS = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

/** "2026-08-10" → Date LOCAL (new Date(iso) interpretaria UTC e andaria um dia
 * para trás no fuso de São Paulo). */
export function parseIsoDay(iso: string): Date {
  const [year = 0, month = 1, day = 1] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function formatIsoDay(day: Date): string {
  const year = day.getFullYear();
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const date = String(day.getDate()).padStart(2, "0");
  return `${year}-${month}-${date}`;
}

/** Convenção §9: DD/MM/AAAA na UI. */
export function formatBrDay(day: Date): string {
  return day.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function addDays(day: Date, amount: number): Date {
  const next = new Date(day);
  next.setDate(next.getDate() + amount);
  return next;
}

export function startOfWeek(day: Date): Date {
  return addDays(day, -day.getDay()); // semana começa no domingo
}

export function startOfMonth(day: Date): Date {
  return new Date(day.getFullYear(), day.getMonth(), 1);
}

/** As 42 células da grade do mês, começando no domingo da semana do dia 1. */
export function monthGridDays(anchor: Date): Date[] {
  const first = startOfWeek(startOfMonth(anchor));
  return Array.from({ length: 42 }, (_, index) => addDays(first, index));
}

/** Intervalo [from, to] (inclusivo) que cada visão pede à API — regra 8 limita a 90
 * dias, e o maior recorte (grade do mês) tem 42. */
export function viewRange(view: ScheduleView, anchor: Date): { from: string; to: string } {
  if (view === "month") {
    const days = monthGridDays(anchor);
    const first = days.at(0);
    const last = days.at(-1);
    if (first === undefined || last === undefined) {
      throw new Error("monthGridDays sempre devolve 42 dias");
    }
    return { from: formatIsoDay(first), to: formatIsoDay(last) };
  }
  if (view === "week") {
    const first = startOfWeek(anchor);
    return { from: formatIsoDay(first), to: formatIsoDay(addDays(first, 6)) };
  }
  if (view === "day") {
    return { from: formatIsoDay(anchor), to: formatIsoDay(anchor) };
  }
  // agenda: os próximos 30 dias a partir da âncora.
  return { from: formatIsoDay(anchor), to: formatIsoDay(addDays(anchor, 29)) };
}

/** Desloca a âncora na unidade da visão (mês/semana/dia) para ‹Anterior/Próximo›. */
export function shiftAnchor(view: ScheduleView, anchor: Date, direction: 1 | -1): Date {
  const next = new Date(anchor);
  if (view === "month") {
    next.setMonth(next.getMonth() + direction);
  } else {
    next.setDate(next.getDate() + direction * (view === "week" ? 7 : 1));
  }
  return next;
}

export function groupByDay(events: ScheduleEvent[]): Map<string, ScheduleEvent[]> {
  const groups = new Map<string, ScheduleEvent[]>();
  for (const event of events) {
    const list = groups.get(event.date) ?? [];
    list.push(event);
    groups.set(event.date, list);
  }
  for (const list of groups.values()) {
    list.sort((a, b) => {
      // Dia inteiro primeiro, depois por hora; sem hora por último entre os com hora.
      if (a.all_day !== b.all_day) return a.all_day ? -1 : 1;
      return (a.scheduled_time ?? "99:99").localeCompare(b.scheduled_time ?? "99:99");
    });
  }
  return groups;
}

export function formatTime(isoTime: string | null): string {
  return isoTime ? isoTime.slice(0, 5) : "";
}

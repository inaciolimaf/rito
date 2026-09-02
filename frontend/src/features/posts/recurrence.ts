/** Recorrência de tarefas (spec 034) — tipos + cálculo puro de datas.
 *
 * Espelha app/domain/posts/recurrence.py: o preview no modal de criação precisa
 * das próximas datas ANTES de o post existir (o endpoint de preview exige um post
 * salvo), então a regra de calendário vive duplicada aqui de propósito — os testes
 * das duas pontas usam os mesmos casos de borda (dia 31, última semana, 29/02).
 *
 * Toda a aritmética é feita em números (ano/mês/dia) com Date.UTC só para dia da
 * semana e soma de dias — nada de `new Date(string)` local, que vira UTC±tz e
 * anda um dia para trás em fusos negativos.
 */

import type { RecurrenceWeek } from "@/lib/domainEnums.generated";

// Reexportado para quem já importava daqui: o nome é o mesmo, a FONTE é o arquivo
// gerado a partir dos `StrEnum` do backend (dívida 15).
export type { RecurrenceWeek };

export type RecurrencePeriod =
  | "DIARIA"
  | "SEMANAL"
  | "QUINZENAL"
  | "MENSAL"
  | "BIMESTRAL"
  | "TRIMESTRAL"
  | "SEMESTRAL"
  | "ANUAL";

export const RECURRENCE_PERIOD_OPTIONS: { value: RecurrencePeriod; label: string }[] = [
  { value: "DIARIA", label: "Diária" },
  { value: "SEMANAL", label: "Semanal" },
  { value: "QUINZENAL", label: "Quinzenal" },
  { value: "MENSAL", label: "Mensal" },
  { value: "BIMESTRAL", label: "Bimestral" },
  { value: "TRIMESTRAL", label: "Trimestral" },
  { value: "SEMESTRAL", label: "Semestral" },
  { value: "ANUAL", label: "Anual" },
];

export const RECURRENCE_WEEK_OPTIONS: { value: RecurrenceWeek; label: string }[] = [
  { value: "DIA_EXATO", label: "No dia exato" },
  { value: "PRIMEIRA", label: "Na 1ª semana do mês" },
  { value: "SEGUNDA", label: "Na 2ª semana do mês" },
  { value: "TERCEIRA", label: "Na 3ª semana do mês" },
  { value: "ULTIMA", label: "Na última semana do mês" },
];

const DAYS_BY_PERIOD: Partial<Record<RecurrencePeriod, number>> = {
  DIARIA: 1,
  SEMANAL: 7,
  // Regra 5: quinzenal = 14 dias corridos, não "duas vezes por mês".
  QUINZENAL: 14,
};

const MONTHS_BY_PERIOD: Partial<Record<RecurrencePeriod, number>> = {
  MENSAL: 1,
  BIMESTRAL: 2,
  TRIMESTRAL: 3,
  SEMESTRAL: 6,
  ANUAL: 12,
};

const WEEK_ORDINAL: Partial<Record<RecurrenceWeek, number>> = {
  PRIMEIRA: 1,
  SEGUNDA: 2,
  TERCEIRA: 3,
};

/** `repeat_on` só faz diferença nas periodicidades mensais ou mais longas. */
export function repeatOnApplies(period: RecurrencePeriod): boolean {
  return MONTHS_BY_PERIOD[period] !== undefined;
}

interface Ymd {
  year: number;
  month: number;
  day: number;
}

function parse(iso: string): Ymd {
  // Defaults silenciam o noUncheckedIndexedAccess — uma data inválida vira NaN e
  // falha feio no preview em vez de virar undefined silencioso.
  const [year = 0, month = 0, day = 0] = iso.split("-").map(Number);
  return { year, month, day };
}

function toIso({ year, month, day }: Ymd): string {
  const mm = String(month).padStart(2, "0");
  const dd = String(day).padStart(2, "0");
  return `${year}-${mm}-${dd}`;
}

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function weekday(year: number, month: number, day: number): number {
  return new Date(Date.UTC(year, month - 1, day)).getUTCDay();
}

function addDays(iso: string, days: number): string {
  const { year, month, day } = parse(iso);
  const next = new Date(Date.UTC(year, month - 1, day + days));
  return toIso({
    year: next.getUTCFullYear(),
    month: next.getUTCMonth() + 1,
    day: next.getUTCDate(),
  });
}

function shiftMonth(year: number, month: number, months: number): [number, number] {
  const zeroBased = month - 1 + months;
  return [year + Math.floor(zeroBased / 12), (((zeroBased % 12) + 12) % 12) + 1];
}

export function nextOccurrence(
  period: RecurrencePeriod,
  repeatOn: RecurrenceWeek,
  anchorIso: string,
  currentIso: string,
): string {
  const days = DAYS_BY_PERIOD[period];
  if (days !== undefined) {
    return addDays(currentIso, days);
  }

  const anchor = parse(anchorIso);
  const current = parse(currentIso);
  const months = MONTHS_BY_PERIOD[period];
  if (months === undefined) {
    throw new Error(`Periodicidade desconhecida: ${period}`);
  }
  const [year, month] = shiftMonth(current.year, current.month, months);
  const anchorWeekday = weekday(anchor.year, anchor.month, anchor.day);

  if (repeatOn === "DIA_EXATO") {
    // Regra 3: o dia vem da ÂNCORA; mês curto clampa no último dia (dia 31 em
    // fevereiro vira 28/29, nunca cai em março; 29/02 anual vira 28/02).
    return toIso({ year, month, day: Math.min(anchor.day, daysInMonth(year, month)) });
  }
  if (repeatOn === "ULTIMA") {
    // Regra 4: última ocorrência do dia da semana no mês — parte do último dia e
    // anda para trás, então resolve igual em meses de 4 e de 5 semanas.
    const lastDay = daysInMonth(year, month);
    const offset = (weekday(year, month, lastDay) - anchorWeekday + 7) % 7;
    return toIso({ year, month, day: lastDay - offset });
  }
  const ordinal = WEEK_ORDINAL[repeatOn];
  if (ordinal === undefined) {
    throw new Error(`Modo de repetição desconhecido: ${repeatOn}`);
  }
  const offset = (anchorWeekday - weekday(year, month, 1) + 7) % 7;
  return toIso({ year, month, day: 1 + offset + 7 * (ordinal - 1) });
}

export interface PreviewOptions {
  period: RecurrencePeriod;
  repeatOn: RecurrenceWeek;
  /** Data do compromisso da primeira ocorrência (a série começa DEPOIS dela). */
  anchor: string;
  count: number;
  untilDate?: string;
  maxOccurrences?: number;
}

export function previewOccurrences({
  period,
  repeatOn,
  anchor,
  count,
  untilDate,
  maxOccurrences,
}: PreviewOptions): string[] {
  const dates: string[] = [];
  let current = anchor;
  // A primeira ocorrência (o template) já conta para o limite (regra 6).
  let created = 1;
  while (dates.length < count) {
    if (maxOccurrences !== undefined && created >= maxOccurrences) {
      break;
    }
    const candidate = nextOccurrence(period, repeatOn, anchor, current);
    if (untilDate !== undefined && untilDate !== "" && candidate > untilDate) {
      break;
    }
    dates.push(candidate);
    current = candidate;
    created += 1;
  }
  return dates;
}

/** DD/MM/AAAA (CLAUDE.md §9 — data na UI é brasileira). */
export function formatBrDate(iso: string): string {
  const { year, month, day } = parse(iso);
  return `${String(day).padStart(2, "0")}/${String(month).padStart(2, "0")}/${year}`;
}

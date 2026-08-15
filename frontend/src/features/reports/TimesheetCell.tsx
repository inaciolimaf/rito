import type { TimesheetDayData } from "@/features/reports/api";

export interface TimesheetCellProps {
  day: TimesheetDayData;
}

function formatTime(value: string | null): string {
  if (!value) return "";
  return new Date(value).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function formatDeviation(minutes: number | null): string | null {
  if (minutes === null) return null;
  if (minutes === 0) return "no horário";
  const sign = minutes > 0 ? "+" : "";
  return `${sign}${minutes} min`;
}

/** Uma célula do livro de ponto (spec 073 §6) — dia sem acesso fica vazio (regra 7,
 * não presume falta); fim de semana/feriado ganham marcador (regra 8); sem jornada
 * cadastrada não mostra desvio (regra 6, nunca "0 min" nesse caso). */
export function TimesheetCell({ day }: TimesheetCellProps): JSX.Element {
  const deviationLabel = formatDeviation(day.deviation_minutes);
  const deviationClass =
    day.deviation_minutes !== null && day.deviation_minutes > 0 ? "text-danger" : "text-muted";

  return (
    <div
      className={
        day.is_weekend || day.is_holiday
          ? "rounded border border-default bg-surface-muted p-2 text-sm"
          : "rounded border border-default bg-surface p-2 text-sm"
      }
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-primary">
          {new Date(`${day.day}T00:00:00`).toLocaleDateString("pt-BR", {
            day: "2-digit",
            weekday: "short",
          })}
        </span>
        {(day.is_weekend || day.is_holiday) && (
          <span className="text-xs text-muted">{day.is_holiday ? "feriado" : "fim de semana"}</span>
        )}
      </div>
      {day.access_count > 0 ? (
        <div className="mt-1 space-y-0.5">
          <p className="text-primary">
            {formatTime(day.first_access)} – {formatTime(day.last_access)}
          </p>
          {deviationLabel && <p className={deviationClass}>{deviationLabel}</p>}
        </div>
      ) : (
        <p className="mt-1 text-muted">—</p>
      )}
    </div>
  );
}

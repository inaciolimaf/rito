// Conversões entre o formato de <input type="time"> ("HH:MM") e o que a API espera
// (spec 012): work_start/work_end como "HH:MM:SS", work_interval como duração ISO 8601
// ("PTxHyM", o que Pydantic devolve para timedelta por padrão).

export function timeInputToApi(value: string): string | null {
  if (!value) return null;
  return `${value}:00`;
}

export function apiTimeToInput(value: string | null): string {
  if (!value) return "";
  return value.slice(0, 5);
}

export function durationInputToApi(value: string): string | null {
  if (!value) return null;
  const [hours, minutes] = value.split(":").map(Number);
  return `PT${hours}H${minutes}M`;
}

export function apiDurationToInput(value: string | null): string {
  if (!value) return "";
  const match = /^PT(?:(\d+)H)?(?:(\d+)M)?/.exec(value);
  if (!match) return "";
  const hours = (match[1] ?? "0").padStart(2, "0");
  const minutes = (match[2] ?? "0").padStart(2, "0");
  return `${hours}:${minutes}`;
}

import {
  formatBrDate,
  previewOccurrences,
  type RecurrencePeriod,
  type RecurrenceWeek,
} from "@/features/posts/recurrence";

export interface RecurrencePreviewProps {
  /** Data do compromisso da primeira ocorrência — vazia desliga o preview. */
  scheduledDate: string;
  period: RecurrencePeriod;
  repeatOn: RecurrenceWeek;
  untilDate?: string;
  maxOccurrences?: number;
  count?: number;
}

/** As próximas datas da série (spec 034 §6) — calculadas no cliente porque o post
 * ainda não existe no modal de criação; depois de salvo, o endpoint
 * /posts/{id}/recurrence/preview responde a mesma coisa (mesma regra, espelhada). */
export function RecurrencePreview({
  scheduledDate,
  period,
  repeatOn,
  untilDate,
  maxOccurrences,
  count = 5,
}: RecurrencePreviewProps): JSX.Element | null {
  if (!scheduledDate) {
    return null;
  }
  const dates = previewOccurrences({
    period,
    repeatOn,
    anchor: scheduledDate,
    count,
    untilDate,
    maxOccurrences,
  });
  if (dates.length === 0) {
    return null;
  }
  return (
    <div className="space-y-1" data-testid="recurrence-preview">
      <p className="text-sm font-medium text-primary">Próximas ocorrências</p>
      <ul className="flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted">
        {dates.map((iso) => (
          <li key={iso}>{formatBrDate(iso)}</li>
        ))}
      </ul>
    </div>
  );
}

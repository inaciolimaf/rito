import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  RECURRENCE_PERIOD_OPTIONS,
  RECURRENCE_WEEK_OPTIONS,
  repeatOnApplies,
  type RecurrencePeriod,
  type RecurrenceWeek,
} from "@/features/posts/recurrence";

export type RecurrenceLimitMode = "none" | "until" | "max";

export interface RecurrenceFieldsValue {
  isRecurring: boolean;
  period: RecurrencePeriod;
  repeatOn: RecurrenceWeek;
  limitMode: RecurrenceLimitMode;
  untilDate: string;
  maxOccurrences: string;
}

export interface RecurrenceFieldsProps {
  value: RecurrenceFieldsValue;
  onChange: (value: RecurrenceFieldsValue) => void;
  error?: string;
}

const LIMIT_OPTIONS: { value: RecurrenceLimitMode; label: string }[] = [
  { value: "none", label: "Sem fim" },
  { value: "until", label: "Até uma data" },
  { value: "max", label: "Nº de ocorrências" },
];

/** Campos da recorrência (spec 034 §6): checkbox "Recorrente" libera periodicidade,
 * modo de repetição (só para mensais — regra: diária/semanal/quinzenal são por dia
 * corrido) e o limite da série (regra 6: until_date OU max_occurrences, o que vier
 * primeiro). */
export function RecurrenceFields({ value, onChange, error }: RecurrenceFieldsProps): JSX.Element {
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-primary">Recorrência</legend>
      <label className="flex items-center gap-2 text-sm text-primary" htmlFor="post-recurring">
        <input
          id="post-recurring"
          type="checkbox"
          checked={value.isRecurring}
          onChange={(event) => onChange({ ...value, isRecurring: event.target.checked })}
        />
        Recorrente
      </label>

      {value.isRecurring && (
        <div className="space-y-2 rounded border border-default p-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="post-recurrence-period">Periodicidade</Label>
              <select
                id="post-recurrence-period"
                className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                value={value.period}
                onChange={(event) =>
                  onChange({ ...value, period: event.target.value as RecurrencePeriod })
                }
              >
                {RECURRENCE_PERIOD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="post-recurrence-repeat-on">Repetir em</Label>
              <select
                id="post-recurrence-repeat-on"
                className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                value={value.repeatOn}
                disabled={!repeatOnApplies(value.period)}
                onChange={(event) =>
                  onChange({ ...value, repeatOn: event.target.value as RecurrenceWeek })
                }
              >
                {RECURRENCE_WEEK_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="post-recurrence-limit">Encerrar</Label>
              <select
                id="post-recurrence-limit"
                className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                value={value.limitMode}
                onChange={(event) =>
                  onChange({ ...value, limitMode: event.target.value as RecurrenceLimitMode })
                }
              >
                {LIMIT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            {value.limitMode === "until" && (
              <div className="space-y-1">
                <Label htmlFor="post-recurrence-until">Até</Label>
                <Input
                  id="post-recurrence-until"
                  type="date"
                  value={value.untilDate}
                  onChange={(event) => onChange({ ...value, untilDate: event.target.value })}
                />
              </div>
            )}
            {value.limitMode === "max" && (
              <div className="space-y-1">
                <Label htmlFor="post-recurrence-max">Ocorrências</Label>
                <Input
                  id="post-recurrence-max"
                  type="number"
                  min={1}
                  value={value.maxOccurrences}
                  onChange={(event) => onChange({ ...value, maxOccurrences: event.target.value })}
                />
              </div>
            )}
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
        </div>
      )}
    </fieldset>
  );
}

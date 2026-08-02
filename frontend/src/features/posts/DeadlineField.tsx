import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface DeadlineFieldProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
}

/** Prazo fatal (spec 032, regra 7) — independente da data do compromisso: pode ser
 * anterior a ela (é o limite jurídico real, não o agendamento). */
export function DeadlineField({ id, value, onChange }: DeadlineFieldProps): JSX.Element {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>Prazo fatal</Label>
      <Input id={id} type="date" value={value} onChange={(event) => onChange(event.target.value)} />
      <p className="text-xs text-muted">Independente da data do compromisso.</p>
    </div>
  );
}

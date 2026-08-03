import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface RetroactiveDateFieldProps {
  id?: string;
  value: string;
  onChange: (value: string) => void;
}

/** Data de conclusão retroativa (spec 033, regra 4): permite o passado — nunca o
 * futuro (o servidor devolve 422 se futura). Vazia = concluir "agora". */
export function RetroactiveDateField({
  id,
  value,
  onChange,
}: RetroactiveDateFieldProps): JSX.Element {
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>Concluir em (retroativo)</Label>
      <Input
        id={id}
        type="date"
        max={today}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <p className="text-xs text-muted">Deixe vazio para concluir agora.</p>
    </div>
  );
}

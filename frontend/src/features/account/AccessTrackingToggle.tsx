import { Checkbox } from "@/components/ui/checkbox";

export interface AccessTrackingToggleProps {
  enabled: boolean;
  disabled?: boolean;
  onChange: (enabled: boolean) => void;
}

/** Spec 073 §5/regra 2 — ligar o rastreamento sempre mostra o aviso de transparência
 * (LGPD): a equipe precisa saber que o acesso passa a ser registrado. */
export function AccessTrackingToggle({
  enabled,
  disabled = false,
  onChange,
}: AccessTrackingToggleProps): JSX.Element {
  return (
    <div className="space-y-2 rounded border border-default bg-surface p-4">
      <label className="flex items-center justify-between gap-4">
        <span>
          <span className="block font-medium text-primary">Rastrear acessos ao sistema</span>
          <span className="block text-sm text-muted">
            Desligado é o padrão — o escritório decide se registra login, IP e horário de cada
            colaborador.
          </span>
        </span>
        <Checkbox
          checked={enabled}
          disabled={disabled}
          onCheckedChange={(checked) => onChange(checked === true)}
        />
      </label>
      {enabled && (
        <p
          role="alert"
          className="rounded border border-warning bg-warning/10 p-2 text-sm text-warning"
        >
          Transparência com a equipe (LGPD): avise os colaboradores de que login, IP e horário de
          acesso passam a ser registrados.
        </p>
      )}
    </div>
  );
}

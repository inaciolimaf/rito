import { AlertTriangle } from "lucide-react";

export interface StaleWarningProps {
  idleCount: number;
}

/** Alerta da aba (spec 074, regra 4): processos ativos parados há mais de 120 dias.
 * Some quando não há nenhum — zero parado não é alerta. */
export function StaleWarning({ idleCount }: StaleWarningProps): JSX.Element | null {
  if (idleCount === 0) return null;
  return (
    <div
      role="alert"
      className="flex items-center gap-2 rounded border border-warning bg-warning/10 px-3 py-2 text-sm text-primary"
    >
      <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />
      <span>
        {idleCount} {idleCount === 1 ? "processo parado" : "processos parados"} há mais de 120 dias.
        Priorize uma movimentação ou o arquivamento.
      </span>
    </div>
  );
}

import { StagnationTooltip } from "@/components/domain/StagnationTooltip";

export interface StagnantBadgeProps {
  daysInStage: number;
  stagnantDays: number | null;
}

/** Badge do card estagnado (spec 052, regra 7): dias na etapa + tooltip explicando
 * a regra da etapa que disparou a marcação. */
export function StagnantBadge({ daysInStage, stagnantDays }: StagnantBadgeProps): JSX.Element {
  const message =
    stagnantDays === null
      ? "Estagnado."
      : `Esta etapa marca como estagnado após ${stagnantDays} dia${stagnantDays === 1 ? "" : "s"} sem mudar de etapa.`;
  return (
    <StagnationTooltip message={message}>
      <span
        data-testid="stagnant-badge"
        tabIndex={0}
        className="inline-flex items-center gap-1 rounded-full bg-danger/15 px-2 py-0.5 text-xs font-medium text-danger"
      >
        Estagnado há {daysInStage} dia{daysInStage === 1 ? "" : "s"}
      </span>
    </StagnationTooltip>
  );
}

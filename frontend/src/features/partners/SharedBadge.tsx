import { Handshake } from "lucide-react";

export interface SharedBadgeProps {
  /** Nome do escritório do outro lado — quando há mais de um, o texto vira a contagem. */
  partnerName?: string | null;
  count?: number;
}

/** Regra 12: processo compartilhado exibe badge permanente — ninguém pode esquecer que
 * há um terceiro escritório olhando. */
export function SharedBadge({ partnerName, count = 1 }: SharedBadgeProps): JSX.Element {
  const label =
    count > 1
      ? `Compartilhado com ${count} parceiros`
      : `Compartilhado com ${partnerName ?? "parceiro"}`;
  return (
    <span
      data-testid="shared-badge"
      title={label}
      className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium text-accent"
    >
      <Handshake aria-hidden className="size-3" />
      {label}
    </span>
  );
}

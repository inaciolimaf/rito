import { Clock } from "lucide-react";

import { cn } from "@/lib/utils";

export interface StalenessIndicatorProps {
  computedAt: string | null;
  isStale: boolean;
}

/** Texto relativo da defasagem ("atualizado há X"). `now` injetável para teste. */
export function formatStaleness(computedAt: string | null, now: Date = new Date()): string {
  if (computedAt === null) return "nunca atualizado";
  const seconds = Math.max(0, Math.floor((now.getTime() - new Date(computedAt).getTime()) / 1000));
  if (seconds < 60) return "atualizado há menos de 1 min";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `atualizado há ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `atualizado há ${hours} h`;
  return `atualizado há ${Math.floor(hours / 24)} d`;
}

/** Indicador de defasagem de um agregado (spec 078, §6): relógio + tooltip
 * "atualizado há X"; amarelo quando a defasagem passa de 2× o intervalo (regra 6). */
export function StalenessIndicator({ computedAt, isStale }: StalenessIndicatorProps): JSX.Element {
  const text = formatStaleness(computedAt);
  const tooltip =
    computedAt === null
      ? "Este agregado ainda não foi atualizado pelo orquestrador."
      : `Dado ${text} (${new Date(computedAt).toLocaleString("pt-BR")}).`;
  return (
    <span
      data-testid="staleness-indicator"
      title={tooltip}
      className={cn(
        "inline-flex items-center gap-1 text-xs",
        isStale ? "text-warning" : "text-muted",
      )}
    >
      <Clock className="h-3.5 w-3.5" aria-hidden="true" />
      {text}
      {isStale && " (desatualizado)"}
    </span>
  );
}

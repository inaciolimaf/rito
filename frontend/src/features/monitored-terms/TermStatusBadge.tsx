import type { TermStatus } from "@/features/monitored-terms/api";

const STATUS_STYLES: Record<TermStatus, { label: string; className: string }> = {
  PENDENTE: { label: "Pendente", className: "bg-surface-muted text-muted" },
  SINCRONIZANDO: { label: "Sincronizando", className: "bg-accent/15 text-accent" },
  ATIVO: { label: "Ativo", className: "bg-success/15 text-success" },
  FALHA: { label: "Falha", className: "bg-danger/15 text-danger" },
  PAUSADO: { label: "Pausado", className: "bg-warning/15 text-warning" },
};

/** Badge dos 5 estados do termo (spec 043 §6) — PENDENTE → SINCRONIZANDO → ATIVO/FALHA,
 * PAUSADO por ação do usuário. Só tokens semânticos (regra rito/no-literal-tailwind-color). */
export function TermStatusBadge({ status }: { status: TermStatus }): JSX.Element {
  const style = STATUS_STYLES[status];
  return (
    <span
      data-testid="term-status-badge"
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${style.className}`}
    >
      {style.label}
    </span>
  );
}

/** Regra 3 (spec 048): cancelada nunca some da lista — ganha badge com o motivo,
 * visível direto na linha da tabela. */
export function CancelledBadge({ reason }: { reason: string | null }): JSX.Element {
  return (
    <span
      title={reason ?? undefined}
      className="inline-block rounded-full bg-danger/15 px-2 py-0.5 text-xs font-medium text-danger"
    >
      Cancelada{reason ? ` — ${reason}` : ""}
    </span>
  );
}

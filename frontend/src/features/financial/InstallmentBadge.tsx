const SUFFIX_PATTERN = /\((\d+)\/(\d+)\)\s*$/;

/** Extrai o "(n/N)" que o backend grava no fim da descrição da parcela (regra 3, spec
 * 057) — sem campo próprio pro total no `TransactionResponse`, o sufixo já é a fonte. */
export function InstallmentBadge({
  description,
}: {
  description: string | null;
}): JSX.Element | null {
  const match = description?.match(SUFFIX_PATTERN);
  if (!match) return null;
  return (
    <span className="ml-2 inline-flex items-center rounded-full bg-surface-muted px-2 py-0.5 text-xs font-medium text-muted">
      {match[1]}/{match[2]}
    </span>
  );
}

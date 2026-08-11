/** Distingue visualmente o lançamento interno na listagem (regra 9, spec 058) — ele
 * aparece junto com os efetivos (filtro padrão é "all"), só marcado como tal. */
export function InternalBadge({ isInternal }: { isInternal: boolean }): JSX.Element | null {
  if (!isInternal) return null;
  return (
    <span
      title="Não entra no saldo, caixa nem DRE — só controle"
      className="ml-2 inline-flex items-center rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent"
    >
      Interno
    </span>
  );
}

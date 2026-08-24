/** Indicador de defasagem dos gráficos de BI (spec 074, regra 8): a view materializada
 * refresca a cada 8 horas, então os números do funil podem estar até 8 h defasados —
 * o aviso é permanente, não condicional. */
export function BiRefreshIndicator({ hint }: { hint: string }): JSX.Element {
  return (
    <p className="text-xs text-muted" data-testid="bi-refresh-indicator">
      {hint}
    </p>
  );
}

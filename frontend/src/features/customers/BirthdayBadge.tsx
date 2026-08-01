export interface BirthdayBadgeProps {
  birthdate: string | null;
}

function isToday(birthdate: string): boolean {
  const today = new Date();
  const [, month, day] = birthdate.split("-").map(Number);
  return month === today.getMonth() + 1 && day === today.getDate();
}

/** Ícone 🎂 quando o aniversário do contato é hoje (ADVBOX §4.5: "notificação de
 * aniversariantes"). Regra 6: ignora o ano, compara só mês e dia. */
export function BirthdayBadge({ birthdate }: BirthdayBadgeProps): JSX.Element | null {
  if (!birthdate || !isToday(birthdate)) return null;
  return (
    <span role="img" aria-label="Aniversariante hoje" title="Aniversariante hoje">
      🎂
    </span>
  );
}

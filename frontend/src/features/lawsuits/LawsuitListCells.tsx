import type { LawsuitListItem } from "@/features/lawsuits/api";

export interface PartiesCellProps {
  parties: LawsuitListItem["parties"];
  partiesTotal: number;
}

/** Coluna de partes (regra 12): as 2 primeiras + contador do restante. */
export function PartiesCell({ parties, partiesTotal }: PartiesCellProps): JSX.Element {
  if (parties.length === 0) return <span className="text-muted">—</span>;
  const shown = parties.slice(0, 2).map((party) => party.name);
  const remaining = partiesTotal - shown.length;
  return (
    <span>
      {shown.join(", ")}
      {remaining > 0 && <span className="text-muted"> +{remaining}</span>}
    </span>
  );
}

const dateFormatter = new Intl.DateTimeFormat("pt-BR");

/** Data do último andamento; "—" quando nunca movimentado. */
export function LastMovementCell({ occurredAt }: { occurredAt: string | null }): JSX.Element {
  if (!occurredAt) return <span className="text-muted">—</span>;
  return <span>{dateFormatter.format(new Date(occurredAt))}</span>;
}

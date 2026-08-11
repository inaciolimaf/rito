import type { EntryType } from "@/features/financial/api";

const NATURE_STYLES: Record<EntryType, string> = {
  RECEITA: "bg-success/15 text-success",
  DESPESA: "bg-muted/15 text-muted",
};

/** Badge do grupo DRE de uma categoria — cor pela natureza (RECEITA/DESPESA) do grupo,
 * não pelo `type` da categoria (regra 2, spec 054: podem divergir nas 2 exceções
 * semeadas do ADVBOX real). */
export function DreGroupBadge({ name, nature }: { name: string; nature: EntryType }): JSX.Element {
  return (
    <span
      data-testid="dre-group-badge"
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${NATURE_STYLES[nature]}`}
    >
      {name}
    </span>
  );
}

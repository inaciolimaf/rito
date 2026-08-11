import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { listFinancialInstitutions } from "@/features/financial/api";

export interface InstitutionSelectProps {
  value: string;
  onChange: (institutionId: string) => void;
  currentLabel?: string | null;
}

async function searchInstitutions(query: string): Promise<EntityOption[]> {
  const institutions = await listFinancialInstitutions(query);
  return institutions.map((item) => ({ id: String(item.id), label: item.name }));
}

/** Busca assíncrona entre as ~95 instituições (spec 055 §6) — muitas pra um `<select>`
 * simples, poucas pra justificar paginação: reaproveita `EntityPicker` como as demais
 * buscas de entidade do produto (spec 007). */
export function InstitutionSelect({
  value,
  onChange,
  currentLabel,
}: InstitutionSelectProps): JSX.Element {
  const selected: EntityOption[] = value ? [{ id: value, label: currentLabel ?? value }] : [];

  return (
    <div className="space-y-1">
      <span className="text-sm font-medium">Instituição</span>
      <EntityPicker
        placeholder="Buscar banco…"
        value={selected}
        onChange={(next) => onChange(next[0]?.id ?? "")}
        onSearch={searchInstitutions}
      />
    </div>
  );
}

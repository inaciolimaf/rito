import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { listFinancialCategories, type EntryType } from "@/features/financial/api";

export interface CategorySelectProps {
  type: EntryType;
  value: EntityOption | null;
  onChange: (option: EntityOption | null) => void;
}

/** Busca assíncrona de categorias filtrada pelo tipo do lançamento (RECEITA/DESPESA) —
 * regra 1 (spec 056): trocar de tipo sem trocar a categoria já escolhida quebraria a
 * validação no backend, então o filtro evita o erro antes de acontecer. Controlado pelo
 * `EntityOption` inteiro (não só o id) — reconstruir o nome a partir do id perderia o
 * rótulo de uma escolha recém-feita (só o registro já carregado da API teria label). */
export function CategorySelect({ type, value, onChange }: CategorySelectProps): JSX.Element {
  async function search(query: string): Promise<EntityOption[]> {
    const page = await listFinancialCategories({ type, status: "active", q: query });
    return page.items.map((item) => ({ id: item.id, label: item.name }));
  }

  return (
    <div className="space-y-1">
      <span className="text-sm font-medium">Categoria</span>
      <EntityPicker
        placeholder="Buscar categoria…"
        value={value ? [value] : []}
        onChange={(next) => onChange(next[0] ?? null)}
        onSearch={search}
      />
    </div>
  );
}

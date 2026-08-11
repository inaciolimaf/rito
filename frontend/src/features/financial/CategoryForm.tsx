import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { DreGroupData } from "@/features/financial/api";
import type { FinancialCategoryFormValues } from "@/features/financial/schema";

export interface CategoryFormProps {
  form: UseFormReturn<FinancialCategoryFormValues>;
  groups: DreGroupData[];
}

/** Nome + tipo + grupo DRE. O select de grupo é filtrado pela natureza do tipo escolhido
 * (§6) — só um guia de UX: o backend não valida type×natureza (regra 2, há exceções reais
 * do ADVBOX), então o grupo já selecionado nunca some da lista mesmo se não bater. */
export function CategoryForm({ form, groups }: CategoryFormProps): JSX.Element {
  const {
    register,
    watch,
    formState: { errors },
  } = form;

  const type = watch("type");
  const currentGroupId = watch("dre_group_id");
  const visibleGroups = groups.filter(
    (group) => group.nature === type || String(group.id) === currentGroupId,
  );

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="category-name">Nome da categoria</Label>
        <Input id="category-name" {...register("name")} />
        {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="category-type">Tipo</Label>
        <select
          id="category-type"
          className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          {...register("type")}
        >
          <option value="RECEITA">Receita</option>
          <option value="DESPESA">Despesa</option>
        </select>
      </div>

      <div className="space-y-1">
        <Label htmlFor="category-group">Grupo DRE</Label>
        <select
          id="category-group"
          className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          {...register("dre_group_id")}
        >
          <option value="">Selecione um grupo</option>
          {visibleGroups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name}
            </option>
          ))}
        </select>
        {errors.dre_group_id && (
          <p className="text-sm text-danger">{errors.dre_group_id.message}</p>
        )}
      </div>
    </>
  );
}

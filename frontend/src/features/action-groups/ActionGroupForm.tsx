import type { UseFormReturn } from "react-hook-form";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ActionGroupFormValues } from "@/features/action-groups/schema";

export interface ActionGroupFormProps {
  form: UseFormReturn<ActionGroupFormValues>;
  onSearchUsers: (query: string) => Promise<EntityOption[]>;
  currentResponsible: EntityOption | null;
}

/** Nome + responsável por intimações opcional (regra 4: vazio cai no responsável geral,
 * spec 045). */
export function ActionGroupForm({
  form,
  onSearchUsers,
  currentResponsible,
}: ActionGroupFormProps): JSX.Element {
  const {
    register,
    watch,
    setValue,
    formState: { errors },
  } = form;

  const publicationsUserId = watch("publications_user_id");
  const selected: EntityOption[] =
    publicationsUserId && currentResponsible?.id === publicationsUserId ? [currentResponsible] : [];

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="action-group-name">Nome do grupo</Label>
        <Input id="action-group-name" {...register("name")} />
        {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="action-group-responsible">Responsável por intimações</Label>
        <EntityPicker
          value={selected}
          onChange={(next) =>
            setValue("publications_user_id", next[0]?.id ?? null, {
              shouldDirty: true,
            })
          }
          onSearch={onSearchUsers}
          label="Responsável por intimações"
          placeholder="Buscar usuário..."
        />
        <p className="text-sm text-muted">
          Vazio: a intimação cai no responsável geral do escritório.
        </p>
      </div>
    </>
  );
}

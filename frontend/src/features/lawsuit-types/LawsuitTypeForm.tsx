import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { LawsuitTypeFormValues } from "@/features/lawsuit-types/schema";

export interface LawsuitTypeFormGroup {
  id: string;
  name: string;
}

export interface LawsuitTypeFormProps {
  form: UseFormReturn<LawsuitTypeFormValues>;
  groups: LawsuitTypeFormGroup[];
}

/** Nome + grupo de ação (regra 2: todo tipo pertence a exatamente um grupo, escolhido aqui —
 * nunca informado direto no processo). */
export function LawsuitTypeForm({ form, groups }: LawsuitTypeFormProps): JSX.Element {
  const {
    register,
    formState: { errors },
  } = form;

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="lawsuit-type-name">Nome do tipo de ação</Label>
        <Input id="lawsuit-type-name" {...register("name")} />
        {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
      </div>

      <div className="space-y-1">
        <Label htmlFor="lawsuit-type-group">Grupo de ação</Label>
        <select
          id="lawsuit-type-group"
          className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          {...register("action_group_id")}
        >
          <option value="">Selecione um grupo</option>
          {groups.map((group) => (
            <option key={group.id} value={group.id}>
              {group.name}
            </option>
          ))}
        </select>
        {errors.action_group_id && (
          <p className="text-sm text-danger">{errors.action_group_id.message}</p>
        )}
      </div>
    </>
  );
}

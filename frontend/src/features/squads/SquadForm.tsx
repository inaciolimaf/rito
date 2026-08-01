import type { UseFormReturn } from "react-hook-form";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { SquadFormValues } from "@/features/squads/schema";

export interface SquadFormUser {
  id: string;
  name: string;
}

export interface SquadFormProps {
  form: UseFormReturn<SquadFormValues>;
  users: SquadFormUser[];
}

/** Nome + checkboxes de colaboradores (spec 013, seção 6) — conteúdo de dentro de um
 * FormModal (regra 2: time pode ser salvo vazio, a UI só avisa, nunca bloqueia). */
export function SquadForm({ form, users }: SquadFormProps): JSX.Element {
  const {
    register,
    watch,
    formState: { errors },
  } = form;

  const selectedCount = watch("member_ids")?.length ?? 0;

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="squad-name">Nome do time</Label>
        <Input id="squad-name" {...register("name")} />
        {errors.name && <p className="text-sm text-danger">{errors.name.message}</p>}
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium text-primary">Membros</legend>
        {users.length === 0 && (
          <p className="text-sm text-muted">Nenhum colaborador cadastrado ainda.</p>
        )}
        <div className="max-h-64 space-y-1 overflow-y-auto rounded border border-default p-2">
          {users.map((user) => (
            <label key={user.id} className="flex items-center gap-2 text-sm text-primary">
              <input type="checkbox" value={user.id} {...register("member_ids")} />
              {user.name}
            </label>
          ))}
        </div>
        {selectedCount === 0 && (
          <p className="text-sm text-muted">
            Este time ficará sem membros — você pode adicionar depois.
          </p>
        )}
      </fieldset>
    </>
  );
}

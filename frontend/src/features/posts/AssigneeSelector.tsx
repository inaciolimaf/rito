import { useQuery } from "@tanstack/react-query";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";
import { Label } from "@/components/ui/label";
import { listSquads } from "@/features/squads/api";

const SELECT_CLASS =
  "h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

export interface AssigneeValue {
  mode: "users" | "squad";
  userIds: EntityOption[];
  squadId: string;
}

export interface AssigneeSelectorProps {
  value: AssigneeValue;
  onChange: (value: AssigneeValue) => void;
  onSearchUsers: (query: string) => Promise<EntityOption[]>;
  error?: string;
}

/** Atribuição da tarefa (spec 032): a usuários (multisseleção) OU a um time inteiro —
 * o servidor expande o time para os membros ativos na criação (regra 2). */
export function AssigneeSelector({
  value,
  onChange,
  onSearchUsers,
  error,
}: AssigneeSelectorProps): JSX.Element {
  const { data: squadsPage } = useQuery({
    queryKey: ["squads", "for-post-form"],
    queryFn: () => listSquads({ status: "active", limit: 100 }),
    enabled: value.mode === "squad",
  });
  const squads = squadsPage?.items ?? [];

  return (
    <div className="space-y-2">
      <div className="flex gap-2" role="group" aria-label="Modo de atribuição">
        <button
          type="button"
          aria-pressed={value.mode === "users"}
          className={
            value.mode === "users"
              ? "rounded border border-accent bg-surface px-3 py-1 text-sm text-primary"
              : "rounded border border-default bg-surface px-3 py-1 text-sm text-muted"
          }
          onClick={() => onChange({ ...value, mode: "users", squadId: "" })}
        >
          Usuários
        </button>
        <button
          type="button"
          aria-pressed={value.mode === "squad"}
          className={
            value.mode === "squad"
              ? "rounded border border-accent bg-surface px-3 py-1 text-sm text-primary"
              : "rounded border border-default bg-surface px-3 py-1 text-sm text-muted"
          }
          onClick={() => onChange({ ...value, mode: "squad", userIds: [] })}
        >
          Time
        </button>
      </div>

      {value.mode === "users" ? (
        <EntityPicker
          multiple
          label="Responsáveis"
          placeholder="Quem vai trabalhar nesta tarefa?"
          value={value.userIds}
          onChange={(userIds) => onChange({ ...value, userIds })}
          onSearch={onSearchUsers}
        />
      ) : (
        <div className="space-y-1">
          <Label htmlFor="post-squad">Time</Label>
          <select
            id="post-squad"
            className={SELECT_CLASS}
            value={value.squadId}
            onChange={(event) => onChange({ ...value, squadId: event.target.value })}
          >
            <option value="">Selecionar time</option>
            {squads.map((squad) => (
              <option key={squad.id} value={squad.id}>
                {squad.name}
              </option>
            ))}
          </select>
        </div>
      )}
      {error && <p className="text-sm text-danger">{error}</p>}
    </div>
  );
}

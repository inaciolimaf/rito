import { useQuery } from "@tanstack/react-query";

import { CrudListPage } from "@/components/domain/CrudListPage";
import type { DataTableColumn } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import {
  createSquad,
  deleteSquad,
  listSquads,
  updateSquad,
  type SquadData,
} from "@/features/squads/api";
import { SquadForm } from "@/features/squads/SquadForm";
import {
  DEFAULT_SQUAD_FORM_VALUES,
  squadFormSchema,
  type SquadFormValues,
} from "@/features/squads/schema";
import { listUsers } from "@/features/users/api";
import { useAuth } from "@/providers/AuthProvider";

const MAX_AVATARS_SHOWN = 3;

export function SquadsListPage(): JSX.Element {
  const { user: currentUser } = useAuth();
  const isAdministrador = currentUser?.role === "ADMINISTRADOR" || currentUser?.role === "GESTOR";

  const { data, isLoading, error } = useQuery({
    queryKey: ["squads"],
    queryFn: () => listSquads({ limit: 50 }),
  });

  const { data: usersPage } = useQuery({
    queryKey: ["users", "for-squad-form"],
    queryFn: () => listUsers({ limit: 100 }),
  });
  const users = usersPage?.items ?? [];

  const crud = useCrudResource<SquadData, SquadFormValues>({
    queryKey: ["squads"],
    create: createSquad,
    update: (squad, values) => updateSquad(squad.id, { ...values, is_active: squad.is_active }),
    remove: (squad) => deleteSquad(squad.id),
  });

  const columns: DataTableColumn<SquadData>[] = [
    { id: "name", header: "Nome do time", cell: (row) => row.name },
    {
      id: "members",
      header: "Membros",
      cell: (row) => (
        <div className="flex items-center gap-1">
          <div className="flex -space-x-2">
            {row.members.slice(0, MAX_AVATARS_SHOWN).map((member) =>
              member.avatar_url ? (
                <img
                  key={member.id}
                  src={member.avatar_url}
                  alt={member.name}
                  className="h-6 w-6 rounded-full border border-surface object-cover"
                />
              ) : (
                <span
                  key={member.id}
                  className="flex h-6 w-6 items-center justify-center rounded-full border border-surface bg-surface-muted text-[10px] text-muted"
                >
                  {member.name.charAt(0).toUpperCase()}
                </span>
              ),
            )}
          </div>
          <span className="text-sm text-muted">{row.members.length}</span>
        </div>
      ),
    },
    {
      id: "created_at",
      header: "Cadastro",
      cell: (row) => new Date(row.created_at).toLocaleDateString("pt-BR"),
    },
  ];

  return (
    <CrudListPage
      title="Times"
      createLabel="Novo time"
      canWrite={isAdministrador}
      columns={columns}
      data={data?.items ?? []}
      isLoading={isLoading}
      error={error}
      emptyMessage="Nenhum time cadastrado ainda."
      crud={crud}
      createTitle="Novo time"
      editTitle="Editar time"
      schema={squadFormSchema}
      emptyFormValues={DEFAULT_SQUAD_FORM_VALUES}
      toFormValues={(squad) => ({
        name: squad.name,
        member_ids: squad.members.map((m) => m.id),
      })}
      formFields={(form) => <SquadForm form={form} users={users} />}
      confirmTitle="Excluir time?"
      confirmDescription={(item) =>
        `"${item?.name ?? ""}" será excluído. Tarefas já atribuídas a partir dele não são afetadas (regra 5).`
      }
    />
  );
}

import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn } from "@/components/domain/types";
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
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

const MAX_AVATARS_SHOWN = 3;

export function SquadsListPage(): JSX.Element {
  const { user: currentUser } = useAuth();
  const isAdministrador = currentUser?.role === "ADMINISTRADOR" || currentUser?.role === "GESTOR";
  const queryClient = useQueryClient();
  const [editingSquad, setEditingSquad] = React.useState<SquadData | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);
  const [formError, setFormError] = React.useState<ApiError | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<SquadData | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["squads"],
    queryFn: () => listSquads({ limit: 50 }),
  });

  const { data: usersPage } = useQuery({
    queryKey: ["users", "for-squad-form"],
    queryFn: () => listUsers({ limit: 100 }),
  });
  const users = usersPage?.items ?? [];

  function openCreateModal(): void {
    setEditingSquad(null);
    setFormError(null);
    setModalOpen(true);
  }

  function openEditModal(squad: SquadData): void {
    setEditingSquad(squad);
    setFormError(null);
    setModalOpen(true);
  }

  async function handleSubmit(values: SquadFormValues): Promise<void> {
    setFormError(null);
    try {
      if (editingSquad) {
        await updateSquad(editingSquad.id, { ...values, is_active: editingSquad.is_active });
      } else {
        await createSquad(values);
      }
      setModalOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["squads"] });
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  async function handleConfirmDelete(): Promise<void> {
    if (!pendingDelete) return;
    await deleteSquad(pendingDelete.id);
    setPendingDelete(null);
    await queryClient.invalidateQueries({ queryKey: ["squads"] });
  }

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
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Times</h1>
        {isAdministrador && <Button onClick={openCreateModal}>Novo time</Button>}
      </div>

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum time cadastrado ainda."
        rowActions={
          isAdministrador
            ? (row) => (
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-sm text-accent underline"
                    onClick={() => openEditModal(row)}
                  >
                    Editar
                  </button>
                  <button
                    type="button"
                    className="text-sm text-danger underline"
                    onClick={() => setPendingDelete(row)}
                  >
                    Excluir
                  </button>
                </div>
              )
            : undefined
        }
      />

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingSquad ? "Editar time" : "Novo time"}
        schema={squadFormSchema}
        defaultValues={
          editingSquad
            ? { name: editingSquad.name, member_ids: editingSquad.members.map((m) => m.id) }
            : DEFAULT_SQUAD_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => <SquadForm form={form} users={users} />}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir time?"
        description={`"${pendingDelete?.name ?? ""}" será excluído. Tarefas já atribuídas a partir dele não são afetadas (regra 5).`}
        confirmLabel="Excluir"
        destructive
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

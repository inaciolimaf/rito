import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import {
  deactivateUser,
  getOccupations,
  inviteUser,
  listUsers,
  type UserData,
} from "@/features/users/api";
import { InviteUserModal } from "@/features/users/InviteUserModal";
import type { InviteUserFormValues } from "@/features/users/schema";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

const FILTER_FIELDS: FilterFieldDef[] = [
  {
    key: "role",
    label: "Perfil",
    type: "select",
    options: [
      { value: "GESTOR", label: "Gestor" },
      { value: "ADMINISTRADOR", label: "Administrador" },
      { value: "COLABORADOR", label: "Colaborador" },
    ],
  },
  {
    key: "status",
    label: "Status",
    type: "select",
    options: [
      { value: "active", label: "Ativo" },
      { value: "inactive", label: "Inativo" },
    ],
  },
  { key: "q", label: "Buscar", type: "text" },
];

const FINANCIAL_LABELS: Record<string, string> = {
  NONE: "Sem acesso",
  READ_ONLY: "Somente visualização",
  FULL: "Acesso completo",
};

const ROLE_LABELS: Record<string, string> = {
  GESTOR: "Gestor",
  ADMINISTRADOR: "Administrador",
  COLABORADOR: "Colaborador",
};

export function UsersListPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";
  const queryClient = useQueryClient();
  const { values } = useFilters(FILTER_FIELDS);
  const [cursorStack, setCursorStack] = React.useState<string[]>([]);
  const [inviteOpen, setInviteOpen] = React.useState(false);
  const [inviteError, setInviteError] = React.useState<ApiError | null>(null);
  const [pendingDeactivation, setPendingDeactivation] = React.useState<UserData | null>(null);

  const currentCursor = cursorStack[cursorStack.length - 1];

  const filters = {
    role: typeof values.role === "string" ? values.role : undefined,
    status:
      typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined,
    q: typeof values.q === "string" ? values.q : undefined,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["users", filters, currentCursor],
    queryFn: () => listUsers({ ...filters, cursor: currentCursor, limit: 20 }),
  });

  const { data: occupations = [] } = useQuery({
    queryKey: ["occupations"],
    queryFn: getOccupations,
  });

  React.useEffect(() => {
    setCursorStack([]);
  }, [filters.role, filters.status, filters.q]);

  const columns: DataTableColumn<UserData>[] = [
    { id: "name", header: "Nome", cell: (row) => row.name },
    { id: "role", header: "Perfil", cell: (row) => ROLE_LABELS[row.role] ?? row.role },
    { id: "points_goal", header: "Meta de pontos", cell: (row) => row.points_goal ?? "—" },
    {
      id: "financial_access",
      header: "Acesso financeiro",
      cell: (row) => FINANCIAL_LABELS[row.financial_access] ?? row.financial_access,
    },
    {
      id: "created_at",
      header: "Cadastro",
      cell: (row) => new Date(row.created_at).toLocaleDateString("pt-BR"),
    },
  ];

  async function handleInvite(formValues: InviteUserFormValues): Promise<void> {
    setInviteError(null);
    try {
      await inviteUser({
        email: formValues.email,
        role: formValues.role,
        financial_access: formValues.financial_access,
        occupation_id: formValues.occupation_id ? Number(formValues.occupation_id) : undefined,
      });
      setInviteOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    } catch (submitError) {
      setInviteError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  async function handleConfirmDeactivate(): Promise<void> {
    if (!pendingDeactivation) return;
    await deactivateUser(pendingDeactivation.id);
    setPendingDeactivation(null);
    await queryClient.invalidateQueries({ queryKey: ["users"] });
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Usuários</h1>
        {isGestor && <Button onClick={() => setInviteOpen(true)}>Convidar usuário</Button>}
      </div>

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum usuário encontrado."
        rowActions={(row) => (
          <div className="flex gap-2">
            <Link to={`/settings/users/${row.id}`} className="text-sm text-accent underline">
              Editar
            </Link>
            {isGestor && row.is_active && (
              <button
                type="button"
                className="text-sm text-danger underline"
                onClick={() => setPendingDeactivation(row)}
              >
                Inativar
              </button>
            )}
          </div>
        )}
        pagination={{
          hasPreviousPage: cursorStack.length > 0,
          hasNextPage: data?.next_cursor != null,
          onPreviousPage: () => setCursorStack((stack) => stack.slice(0, -1)),
          onNextPage: () => {
            if (data?.next_cursor) {
              setCursorStack((stack) => [...stack, data.next_cursor as string]);
            }
          },
        }}
      />

      <InviteUserModal
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        occupations={occupations}
        serverError={inviteError}
        onSubmit={handleInvite}
      />

      <ConfirmDialog
        open={pendingDeactivation !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDeactivation(null);
        }}
        title="Inativar usuário?"
        description={`${pendingDeactivation?.name ?? ""} não vai mais aparecer nas listas de atribuição — o histórico permanece (regra 7).`}
        confirmLabel="Inativar"
        destructive
        onConfirm={handleConfirmDeactivate}
      />
    </div>
  );
}

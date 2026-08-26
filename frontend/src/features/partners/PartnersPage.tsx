import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { EmptyState } from "@/components/domain/EmptyState";
import { StatCard } from "@/components/domain/StatCard";
import type { DataTableColumn } from "@/components/domain/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  acceptPartnership,
  endPartnership,
  getPartnershipSummary,
  invitePartner,
  listPartnerships,
  listSharedWithMe,
  type PartnershipData,
  type SharedWithMeItem,
} from "@/features/partners/api";
import { InvitePartnerDialog } from "@/features/partners/InvitePartnerDialog";
import { PartnerNetworkList } from "@/features/partners/PartnerNetworkList";
import { useAuth } from "@/providers/AuthProvider";

const SHARED_COLUMNS: DataTableColumn<SharedWithMeItem>[] = [
  { id: "owner", header: "Escritório", cell: (row) => row.owner_name },
  {
    id: "process",
    header: "Processo",
    cell: (row) => row.process_number ?? row.folder ?? "Sem número",
  },
  { id: "stage", header: "Fase", cell: (row) => row.stage_name },
  { id: "open_tasks", header: "Tarefas em aberto", cell: (row) => row.open_tasks },
  {
    id: "scope",
    header: "Escopo",
    cell: (row) =>
      [row.can_view_financial ? "Valores" : null, row.can_create_tasks ? "Criar tarefas" : null]
        .filter(Boolean)
        .join(" · ") || "Somente leitura",
  },
];

/** Tela de parceiros (spec 079 §6): cards de demanda, rede de parceiros e os processos
 * que outros escritórios compartilharam com este. */
export function PartnersPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";
  const queryClient = useQueryClient();
  const [inviteOpen, setInviteOpen] = React.useState(false);
  const [pendingEnd, setPendingEnd] = React.useState<PartnershipData | null>(null);
  const [token, setToken] = React.useState("");
  const [acceptError, setAcceptError] = React.useState<string | null>(null);

  const { data: summary } = useQuery({
    queryKey: ["partnerships", "summary"],
    queryFn: getPartnershipSummary,
  });
  const { data: partnerships, isLoading } = useQuery({
    queryKey: ["partnerships"],
    queryFn: () => listPartnerships(),
  });
  const { data: shared } = useQuery({
    queryKey: ["partnerships", "shared-with-me"],
    queryFn: () => listSharedWithMe(),
  });

  const invalidate = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: ["partnerships"] }).then(() => undefined);

  const accept = useMutation({
    mutationFn: (value: string) => acceptPartnership(value),
    onSuccess: () => {
      setToken("");
      setAcceptError(null);
      return invalidate();
    },
    onError: () => setAcceptError("Convite inválido ou já utilizado."),
  });
  const end = useMutation({
    mutationFn: (partnership: PartnershipData) => endPartnership(partnership.id),
    onSuccess: invalidate,
  });

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Parceiros</h1>
        {isGestor && (
          <Button type="button" onClick={() => setInviteOpen(true)}>
            Convidar parceiro
          </Button>
        )}
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Processos compartilhados" value={summary?.shared_lawsuits ?? 0} />
        <StatCard
          label="Demanda pendente pelo escritório"
          value={summary?.pending_by_office ?? 0}
        />
        <StatCard label="Demanda pendente pelo parceiro" value={summary?.pending_by_partner ?? 0} />
      </div>

      {isGestor && (
        <form
          className="flex items-end gap-2 rounded border border-default bg-surface p-4"
          onSubmit={(event) => {
            event.preventDefault();
            accept.mutate(token);
          }}
        >
          <div className="flex-1 space-y-1">
            <Label htmlFor="accept-token">Recebeu um convite? Cole o código aqui</Label>
            <Input
              id="accept-token"
              value={token}
              onChange={(event) => setToken(event.target.value)}
              autoComplete="off"
            />
          </div>
          <Button type="submit" disabled={!token}>
            Aceitar convite
          </Button>
        </form>
      )}
      {acceptError && (
        <p role="alert" className="text-sm text-danger">
          {acceptError}
        </p>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-primary">Rede de parceiros</h2>
        <PartnerNetworkList
          partnerships={partnerships?.items ?? []}
          isLoading={isLoading}
          onEnd={setPendingEnd}
        />
      </section>

      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-primary">Compartilhados comigo</h2>
        {(shared?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="Nenhum processo compartilhado com você"
            description="Quando um parceiro compartilhar um processo, ele aparece aqui — só ele, nada mais da carteira dele."
          />
        ) : (
          <DataTable
            data={shared?.items ?? []}
            columns={SHARED_COLUMNS}
            getRowId={(row) => row.share_id}
          />
        )}
      </section>

      <InvitePartnerDialog
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        onInvite={async (email) => {
          const result = await invitePartner(email);
          await invalidate();
          return result;
        }}
      />
      <ConfirmDialog
        open={pendingEnd !== null}
        onOpenChange={(open) => !open && setPendingEnd(null)}
        title="Encerrar parceria"
        description="Encerrar revoga TODOS os compartilhamentos entre os dois escritórios, imediatamente e dos dois lados."
        confirmLabel="Encerrar"
        destructive
        onConfirm={async () => {
          if (pendingEnd) await end.mutateAsync(pendingEnd);
          setPendingEnd(null);
        }}
      />
    </div>
  );
}

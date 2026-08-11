import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useFilters } from "@/components/domain/useFilters";
import { listStates } from "@/features/locations/api";
import {
  createMonitoredTerm,
  deleteMonitoredTerm,
  listMonitoredTerms,
  listTermSyncRuns,
  pauseMonitoredTerm,
  resumeMonitoredTerm,
  syncMonitoredTerm,
  updateMonitoredTerm,
  type MonitoredTermData,
  type TermKind,
  type TermStatus,
} from "@/features/monitored-terms/api";
import { MonitoredTermForm } from "@/features/monitored-terms/MonitoredTermForm";
import {
  DEFAULT_MONITORED_TERM_FORM_VALUES,
  monitoredTermFormSchema,
  type MonitoredTermFormValues,
} from "@/features/monitored-terms/schema";
import { SyncRunsTable } from "@/features/monitored-terms/SyncRunsTable";
import { TermHealthCard } from "@/features/monitored-terms/TermHealthCard";
import { TermStatusBadge } from "@/features/monitored-terms/TermStatusBadge";
import { listUsers } from "@/features/users/api";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

const FILTER_FIELDS: FilterFieldDef[] = [
  {
    key: "status",
    label: "Status",
    type: "select",
    options: [
      { value: "PENDENTE", label: "Pendente" },
      { value: "SINCRONIZANDO", label: "Sincronizando" },
      { value: "ATIVO", label: "Ativo" },
      { value: "FALHA", label: "Falha" },
      { value: "PAUSADO", label: "Pausado" },
    ],
  },
  {
    key: "kind",
    label: "Tipo",
    type: "select",
    options: [
      { value: "OAB", label: "OAB" },
      { value: "CPF", label: "CPF" },
      { value: "CNPJ", label: "CNPJ" },
    ],
  },
  { key: "q", label: "Buscar", type: "text" },
];

function formatTerm(term: MonitoredTermData): string {
  return term.kind === "OAB" ? `OAB/${term.oab_state ?? ""} ${term.value}` : term.value;
}

/** Configurações > Termos monitorados (spec 043 §6). */
export function MonitoredTermsListPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR" || user?.role === "ADMINISTRADOR";
  const isAdministrador = user?.role === "ADMINISTRADOR";
  const queryClient = useQueryClient();
  const [runsTerm, setRunsTerm] = React.useState<MonitoredTermData | null>(null);

  const { values } = useFilters(FILTER_FIELDS);
  const status = typeof values.status === "string" ? (values.status as TermStatus) : undefined;
  const kind = typeof values.kind === "string" ? (values.kind as TermKind) : undefined;
  const q = typeof values.q === "string" ? values.q : undefined;

  const { data, isLoading, error } = useQuery({
    queryKey: ["monitored-terms", { status, kind, q }],
    queryFn: () => listMonitoredTerms({ status, kind, q }),
  });
  const { data: states = [] } = useQuery({ queryKey: ["states"], queryFn: listStates });
  const { data: usersPage } = useQuery({
    queryKey: ["users", "monitored-terms"],
    queryFn: () => listUsers({ limit: 100 }),
  });
  const { data: runsPage, isLoading: runsLoading } = useQuery({
    queryKey: ["monitored-terms", runsTerm?.id, "runs"],
    queryFn: () => listTermSyncRuns(runsTerm?.id ?? ""),
    enabled: runsTerm !== null,
  });

  const invalidate = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: ["monitored-terms"] }).then(() => undefined);

  const pauseResume = useMutation({
    mutationFn: (term: MonitoredTermData) =>
      term.status === "PAUSADO" ? resumeMonitoredTerm(term.id) : pauseMonitoredTerm(term.id),
    onSuccess: invalidate,
  });
  const syncNow = useMutation({
    mutationFn: (term: MonitoredTermData) => syncMonitoredTerm(term.id),
    onSuccess: invalidate,
  });

  const {
    editing,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
    handleConfirmDelete,
  } = useCrudResource<MonitoredTermData, MonitoredTermFormValues>({
    queryKey: ["monitored-terms"],
    create: (values) =>
      createMonitoredTerm({
        kind: values.kind,
        value: values.value,
        oab_state: values.kind === "OAB" ? values.oab_state || null : null,
        label: values.label || null,
        user_id: values.user_id || null,
        backfill_from: values.backfill_from || null,
      }),
    update: (term, values) =>
      updateMonitoredTerm(term.id, {
        label: values.label || null,
        user_id: values.user_id || null,
        backfill_from: values.backfill_from || null,
        is_active: term.is_active,
      }),
    remove: (term) => deleteMonitoredTerm(term.id),
  });

  const columns: DataTableColumn<MonitoredTermData>[] = [
    { id: "value", header: "Termo", cell: (row) => formatTerm(row) },
    { id: "kind", header: "Tipo", cell: (row) => row.kind },
    {
      id: "user",
      header: "Responsável",
      cell: (row) => usersPage?.items.find((option) => option.id === row.user_id)?.name ?? "—",
    },
    {
      id: "status",
      header: "Status",
      cell: (row) => <TermStatusBadge status={row.status} />,
    },
    {
      id: "last_sync_at",
      header: "Última sincronização",
      cell: (row) => (row.last_sync_at ? new Date(row.last_sync_at).toLocaleString("pt-BR") : "—"),
    },
    { id: "captured_count", header: "Capturadas", cell: (row) => row.captured_count },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Termos monitorados</h1>
        {isGestor && <Button onClick={openCreateModal}>Novo termo</Button>}
      </div>

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum termo monitorado cadastrado ainda."
        rowActions={(row) => (
          <div className="flex gap-2">
            {isAdministrador && (
              <button
                type="button"
                className="text-sm text-accent underline"
                onClick={() => setRunsTerm(row)}
              >
                Histórico
              </button>
            )}
            {isAdministrador && (
              <button
                type="button"
                className="text-sm text-accent underline"
                disabled={syncNow.isPending}
                onClick={() => syncNow.mutate(row)}
              >
                Sincronizar
              </button>
            )}
            {isGestor && (
              <button
                type="button"
                className="text-sm text-accent underline"
                onClick={() => openEditModal(row)}
              >
                Editar
              </button>
            )}
            {isGestor && (
              <button
                type="button"
                className="text-sm text-accent underline"
                disabled={pauseResume.isPending}
                onClick={() => pauseResume.mutate(row)}
              >
                {row.status === "PAUSADO" ? "Retomar" : "Pausar"}
              </button>
            )}
            {isGestor && (
              <button
                type="button"
                className="text-sm text-danger underline"
                onClick={() => setPendingDelete(row)}
              >
                Excluir
              </button>
            )}
          </div>
        )}
      />

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editing ? "Editar termo" : "Novo termo monitorado"}
        schema={monitoredTermFormSchema}
        defaultValues={
          editing
            ? {
                kind: editing.kind,
                value: editing.value,
                oab_state: editing.oab_state ?? "",
                label: editing.label ?? "",
                user_id: editing.user_id ?? "",
                backfill_from: editing.backfill_from ?? "",
              }
            : DEFAULT_MONITORED_TERM_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => <MonitoredTermForm form={form} states={states} users={usersPage?.items ?? []} />}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir termo monitorado?"
        description={`"${pendingDelete ? formatTerm(pendingDelete) : ""}" deixará de ser vigiado. As publicações já capturadas são preservadas.`}
        confirmLabel="Excluir"
        destructive
        onConfirm={handleConfirmDelete}
      />

      <Dialog open={runsTerm !== null} onOpenChange={(open) => !open && setRunsTerm(null)}>
        <DialogContent>
          <DialogTitle>Histórico — {runsTerm ? formatTerm(runsTerm) : ""}</DialogTitle>
          {runsTerm && <TermHealthCard termId={runsTerm.id} />}
          {runsLoading ? (
            <p className="text-sm text-muted">Carregando…</p>
          ) : (
            <SyncRunsTable runs={runsPage?.items ?? []} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

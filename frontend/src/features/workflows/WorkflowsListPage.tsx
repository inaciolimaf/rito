import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { Button } from "@/components/ui/button";
import {
  createWorkflow,
  deleteWorkflow,
  getWorkflow,
  listWorkflows,
  updateWorkflow,
  type WorkflowDetail,
  type WorkflowListItem,
} from "@/features/workflows/api";
import { WorkflowEditor } from "@/features/workflows/WorkflowEditor";
import { WorkflowPreviewDialog } from "@/features/workflows/WorkflowPreviewDialog";
import { useAuth } from "@/providers/AuthProvider";

const FILTER_FIELDS: FilterFieldDef[] = [
  { key: "q", label: "Buscar", type: "text" },
  {
    key: "status",
    label: "Status",
    type: "select",
    options: [
      { value: "active", label: "Ativos" },
      { value: "inactive", label: "Inativos" },
    ],
  },
];

/** Cadastro de workflows (spec 038 §6, rota /settings/workflows): lista + editor de
 * sequência + aplicação manual a um processo (§2). Escrita só para GESTOR (§5). */
export function WorkflowsListPage(): JSX.Element {
  const { user } = useAuth();
  const isGestor = user?.role === "GESTOR";
  const queryClient = useQueryClient();

  const { values } = useFilters(FILTER_FIELDS);
  const q = typeof values.q === "string" ? values.q : undefined;
  const status = typeof values.status === "string" ? values.status : undefined;

  const { data: workflows = [], isLoading } = useQuery({
    queryKey: ["workflows", status, q],
    queryFn: () => listWorkflows({ status, q }),
  });

  const [editorOpen, setEditorOpen] = React.useState(false);
  const [editing, setEditing] = React.useState<WorkflowDetail | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<WorkflowListItem | null>(null);
  const [applying, setApplying] = React.useState<WorkflowListItem | null>(null);

  async function invalidate(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["workflows"] });
  }

  async function openEdit(item: WorkflowListItem): Promise<void> {
    setEditing(await getWorkflow(item.id));
    setEditorOpen(true);
  }

  async function handleConfirmDelete(): Promise<void> {
    if (!pendingDelete) return;
    // Regra 9: tarefas já criadas não são afetadas pela exclusão.
    await deleteWorkflow(pendingDelete.id);
    setPendingDelete(null);
    await invalidate();
  }

  const columns: DataTableColumn<WorkflowListItem>[] = [
    { id: "name", header: "Nome", cell: (row) => row.name },
    { id: "step_count", header: "Etapas", cell: (row) => row.step_count },
    {
      id: "is_active",
      header: "Status",
      cell: (row) =>
        row.is_active ? (
          <span className="text-success">Ativo</span>
        ) : (
          <span className="text-muted">Inativo</span>
        ),
    },
  ];

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Workflows</h1>
        {isGestor && (
          <Button
            type="button"
            onClick={() => {
              setEditing(null);
              setEditorOpen(true);
            }}
          >
            Novo workflow
          </Button>
        )}
      </div>

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={workflows}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        emptyMessage="Nenhum workflow cadastrado."
        rowActions={(row) => (
          <div className="flex gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={() => setApplying(row)}>
              Aplicar
            </Button>
            {isGestor && (
              <>
                <Button type="button" variant="ghost" size="sm" onClick={() => void openEdit(row)}>
                  Editar
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setPendingDelete(row)}
                >
                  Excluir
                </Button>
              </>
            )}
          </div>
        )}
      />

      <WorkflowEditor
        open={editorOpen}
        onOpenChange={setEditorOpen}
        initial={editing}
        onSubmit={async (payload) => {
          if (editing) {
            await updateWorkflow(editing.id, payload);
          } else {
            await createWorkflow(payload);
          }
          await invalidate();
        }}
      />

      <WorkflowPreviewDialog
        open={applying !== null}
        onOpenChange={(open) => {
          if (!open) setApplying(null);
        }}
        workflowId={applying?.id ?? null}
        workflowName={applying?.name}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title={`Excluir o workflow "${pendingDelete?.name}"?`}
        description="As tarefas já criadas por ele nos processos não são afetadas."
        confirmLabel="Excluir"
        destructive
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

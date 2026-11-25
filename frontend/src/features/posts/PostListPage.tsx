import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { EmptyState } from "@/components/domain/EmptyState";
import { ListPageLayout } from "@/components/domain/ListPageLayout";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { useListPage } from "@/components/domain/useListPage";
import { Button } from "@/components/ui/button";
import { bulkComplete } from "@/features/inbox/api";
import { PriorityBadge } from "@/features/posts/PriorityBadge";
import {
  exportActivities,
  listActivities,
  type ActivityFilters,
  type ActivityListItem,
} from "@/features/posts/api";
import { listTaskTypes } from "@/features/task-types/api";
import { listUsers } from "@/features/users/api";
import { useAuth } from "@/providers/AuthProvider";

const STATUS_LABELS: Record<ActivityListItem["status"], string> = {
  PENDENTE: "Pendente",
  CONCLUIDA: "Concluída",
  ATRASADA: "Atrasada",
};

const STATUS_CLASSES: Record<ActivityListItem["status"], string> = {
  PENDENTE: "text-muted",
  CONCLUIDA: "text-success",
  ATRASADA: "text-danger",
};

/** `DD/MM/AAAA` (CLAUDE.md §9). A API fala ISO 8601; a tela, brasileiro. */
function brDate(value: string | null): string {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function textFilter(values: Record<string, unknown>, key: string): string | undefined {
  const value = values[key];
  return typeof value === "string" && value !== "" ? value : undefined;
}

/** Tela de Atividades (spec 128): a lista global de tarefas do escritório.
 *
 * O item "Atividades" do menu aponta para `/posts` desde a spec 008 e caía num redirect
 * para `/home` (dívida técnica nº 26) porque a tela nunca existiu. Ela é a `/customers`
 * das tarefas — e, como toda listagem depois da 007, é declaração de colunas e de
 * filtros: nenhuma tabela, filtro ou paginação escrita aqui. */
export function PostListPage(): JSX.Element {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Regra 9 da spec 033: fechar a linha de outro responsável exige ADMINISTRADOR, e numa
  // lista global a seleção quase sempre pega linha de terceiro. Sem o perfil, a ação em
  // massa não é renderizada — o colaborador conclui as dele pela caixa de entrada.
  const canBulkComplete = user?.role === "GESTOR" || user?.role === "ADMINISTRADOR";

  const { data: taskTypes } = useQuery({
    queryKey: ["task-types", "for-activity-filters"],
    queryFn: () => listTaskTypes({ status: "active" }),
  });
  const { data: usersPage } = useQuery({
    queryKey: ["users", "for-activity-filters"],
    queryFn: () => listUsers({ status: "active", limit: 100 }),
  });

  const filterFields: FilterFieldDef[] = [
    {
      key: "view",
      label: "Situação",
      type: "select",
      options: [
        { value: "pending", label: "Pendentes" },
        { value: "overdue", label: "Atrasadas" },
        { value: "completed", label: "Concluídas" },
        { value: "all", label: "Todas" },
      ],
    },
    {
      key: "column",
      label: "Período por",
      type: "select",
      options: [
        { value: "scheduled", label: "Data do compromisso" },
        { value: "deadline", label: "Prazo fatal" },
        { value: "completed", label: "Data de conclusão" },
        { value: "created", label: "Data de criação" },
      ],
    },
    { key: "date_from", label: "De", type: "date" },
    { key: "date_to", label: "Até", type: "date" },
    {
      key: "task_type_id",
      label: "Tarefa",
      type: "select",
      options: (taskTypes?.items ?? []).map((item) => ({ value: item.id, label: item.name })),
    },
    {
      key: "assignee_id",
      label: "Responsável",
      type: "select",
      options: (usersPage?.items ?? []).map((item) => ({ value: item.id, label: item.name })),
    },
    {
      key: "sender",
      label: "Origem",
      type: "select",
      options: [
        { value: "received", label: "Que eu recebi" },
        { value: "sent", label: "Que eu enviei" },
      ],
    },
    {
      key: "priority",
      label: "Prioridade",
      type: "select",
      options: [
        { value: "urgent", label: "Urgentes" },
        { value: "important", label: "Importantes" },
        { value: "important,urgent", label: "Urgentes ou importantes" },
      ],
    },
    { key: "include_future", label: "Mostrar futuras", type: "boolean" },
  ];

  const { values } = useFilters(filterFields);
  const view = (textFilter(values, "view") ?? "pending") as ActivityFilters["view"];
  const column = (textFilter(values, "column") ?? "scheduled") as ActivityFilters["column"];
  const dateFrom = textFilter(values, "date_from");
  const dateTo = textFilter(values, "date_to");
  const taskTypeId = textFilter(values, "task_type_id");
  const assigneeId = textFilter(values, "assignee_id");
  const sender = textFilter(values, "sender") as ActivityFilters["sender"];
  const priority = textFilter(values, "priority");
  const includeFuture = values.include_future === "true";

  const filters: ActivityFilters = {
    view,
    column,
    date_from: dateFrom,
    date_to: dateTo,
    task_type_id: taskTypeId,
    assignee_id: assigneeId,
    sender,
    priority,
    include_future: includeFuture,
  };

  const listPage = useListPage({
    queryKey: "activities",
    filters,
    fetchPage: listActivities,
    exportFile: exportActivities,
    resetDeps: [
      view,
      column,
      dateFrom,
      dateTo,
      taskTypeId,
      assigneeId,
      sender,
      priority,
      includeFuture,
    ],
  });

  const [selectedIds, setSelectedIds] = React.useState<Set<string>>(new Set());
  const [pendingComplete, setPendingComplete] = React.useState<string[] | null>(null);

  async function handleConfirmComplete(): Promise<void> {
    if (!pendingComplete) return;
    await bulkComplete(pendingComplete);
    setPendingComplete(null);
    setSelectedIds(new Set());
    await queryClient.invalidateQueries({ queryKey: ["activities"] });
  }

  const columns: DataTableColumn<ActivityListItem>[] = [
    {
      id: "task_type_name",
      header: "Tarefa",
      cell: (row) => (
        <span className="flex items-center gap-2">
          {row.task_type_name}
          <PriorityBadge
            isImportant={row.is_important}
            isUrgent={row.is_urgent}
            isPrivate={row.is_private}
          />
        </span>
      ),
    },
    {
      id: "lawsuit",
      header: "Processo",
      cell: (row) => (
        <button
          type="button"
          className="text-accent underline"
          onClick={() => navigate(`/lawsuits/${row.lawsuit_id}`)}
        >
          {row.process_number ?? row.folder ?? "Sem número"}
        </button>
      ),
    },
    {
      id: "assignees",
      header: "Responsáveis",
      cell: (row) => (row.assignee_names.length > 0 ? row.assignee_names.join(", ") : "—"),
    },
    {
      id: "scheduled_date",
      header: "Data do compromisso",
      cell: (row) => brDate(row.scheduled_date),
    },
    { id: "deadline_date", header: "Prazo fatal", cell: (row) => brDate(row.deadline_date) },
    {
      id: "status",
      header: "Status",
      cell: (row) => (
        <span className={STATUS_CLASSES[row.status]}>{STATUS_LABELS[row.status]}</span>
      ),
    },
  ];

  const items = listPage.items;
  // "Sem filtro" é a tela recém-aberta: só a situação padrão marcada. É o que separa
  // "o escritório não tem atividade nenhuma" de "este filtro não achou nada".
  const hasActiveFilters =
    Object.entries(values).filter(([key]) => key !== "view" && key !== "column").length > 0 ||
    view !== "pending";

  return (
    <ListPageLayout
      title="Atividades"
      filterFields={filterFields}
      actions={
        <>
          <Button variant="outline" onClick={() => void listPage.exportAs("xlsx")}>
            Exportar XLSX
          </Button>
          <Button variant="outline" onClick={() => void listPage.exportAs("pdf")}>
            Exportar PDF
          </Button>
        </>
      }
    >
      {items.length === 0 && !listPage.isLoading && !listPage.error && !hasActiveFilters ? (
        <EmptyState
          title="Nenhuma atividade pendente"
          description="As tarefas do escritório aparecem aqui. Crie a primeira a partir de um processo."
          action={{ label: "Ir para a caixa de entrada", onClick: () => navigate("/home") }}
        />
      ) : (
        <DataTable
          columns={columns}
          data={items}
          getRowId={(row) => row.id}
          isLoading={listPage.isLoading}
          error={listPage.error}
          emptyMessage="Nenhuma atividade encontrada com esses filtros."
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          bulkActions={
            canBulkComplete
              ? [{ label: "Concluir selecionadas", onClick: (ids) => setPendingComplete(ids) }]
              : undefined
          }
          rowActions={(row) => (
            <button
              type="button"
              className="text-sm text-accent underline"
              onClick={() => navigate(`/posts/${row.id}`)}
            >
              Abrir
            </button>
          )}
          pagination={listPage.pagination}
        />
      )}

      <ConfirmDialog
        open={pendingComplete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingComplete(null);
        }}
        title="Concluir as atividades selecionadas?"
        description={`${pendingComplete?.length ?? 0} atividade(s) serão concluídas — a pontuação é creditada a cada responsável.`}
        confirmLabel="Concluir"
        onConfirm={handleConfirmComplete}
      />
    </ListPageLayout>
  );
}

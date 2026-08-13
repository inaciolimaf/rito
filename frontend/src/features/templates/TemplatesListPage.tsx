import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useFilters } from "@/components/domain/useFilters";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  createTemplate,
  deleteTemplate,
  duplicateTemplate,
  listTemplates,
  restoreTemplate,
  updateTemplate,
  type TemplateData,
  type TemplateType,
  type TemplateView,
} from "@/features/templates/api";
import {
  DEFAULT_TEMPLATE_FORM_VALUES,
  templateFormSchema,
  type TemplateFormValues,
} from "@/features/templates/schema";
import { ApiError } from "@/lib/errors";

const TYPE_LABELS: Record<TemplateType, string> = {
  CONTRATO: "Contrato",
  PETICAO: "Petição",
  RECURSO: "Recurso",
  DOCUMENTO: "Documento",
};

const FILTER_FIELDS: FilterFieldDef[] = [
  {
    key: "view",
    label: "Tipo",
    type: "select",
    options: [
      { value: "all", label: "Todos" },
      { value: "CONTRATO", label: "Contratos" },
      { value: "PETICAO", label: "Petições" },
      { value: "RECURSO", label: "Recursos" },
      { value: "DOCUMENTO", label: "Documentos" },
      { value: "trash", label: "Somente os excluídos" },
    ],
  },
  { key: "q", label: "Buscar por nome", type: "text" },
];

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("pt-BR");
}

/** Biblioteca de modelos (spec 064) — o editor rico (spec 065) e as variáveis (spec
 * 066) chegam depois; aqui é só cadastro, tipo, busca e lixeira reversível. */
export function TemplatesListPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { values } = useFilters(FILTER_FIELDS);
  const view = typeof values.view === "string" ? (values.view as TemplateView) : "all";
  const q = typeof values.q === "string" ? values.q : undefined;
  const isTrash = view === "trash";

  const { data, isLoading, error } = useQuery({
    queryKey: ["templates", { view, q }],
    queryFn: () => listTemplates({ view, q }),
  });

  const {
    editing: editingTemplate,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
    handleConfirmDelete,
  } = useCrudResource<TemplateData, TemplateFormValues>({
    queryKey: ["templates"],
    create: createTemplate,
    update: (template, formValues) => updateTemplate(template.id, formValues),
    remove: (template) => deleteTemplate(template.id),
  });

  const restore = useMutation({
    mutationFn: (id: string) => restoreTemplate(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["templates"] }),
  });

  const duplicate = useMutation({
    mutationFn: (id: string) => duplicateTemplate(id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["templates"] }),
  });

  const columns: DataTableColumn<TemplateData>[] = [
    { id: "name", header: "Nome", cell: (row) => row.name },
    { id: "type", header: "Tipo", cell: (row) => TYPE_LABELS[row.type] },
    { id: "created_at", header: "Cadastro", cell: (row) => formatDate(row.created_at) },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Modelos</h1>
        <Button onClick={openCreateModal}>Novo modelo</Button>
      </div>

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={data?.items ?? []}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage={isTrash ? "A lixeira está vazia." : "Nenhum modelo cadastrado ainda."}
        rowActions={(row) => (
          <div className="flex gap-2">
            {isTrash ? (
              <button
                type="button"
                className="text-sm text-accent underline"
                onClick={() => restore.mutate(row.id)}
              >
                Restaurar
              </button>
            ) : (
              <>
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
              </>
            )}
            <button
              type="button"
              className="text-sm text-accent underline"
              onClick={() => duplicate.mutate(row.id)}
            >
              Fazer cópia
            </button>
          </div>
        )}
      />

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingTemplate ? "Editar modelo" : "Novo modelo"}
        schema={templateFormSchema}
        defaultValues={editingTemplate ? { ...editingTemplate } : DEFAULT_TEMPLATE_FORM_VALUES}
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <>
            <div className="space-y-1">
              <Label htmlFor="template-name">Nome</Label>
              <Input id="template-name" {...form.register("name")} />
              {form.formState.errors.name && (
                <p className="text-sm text-danger">{form.formState.errors.name.message}</p>
              )}
            </div>
            <div className="space-y-1">
              <Label htmlFor="template-type">Tipo</Label>
              <select
                id="template-type"
                className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                {...form.register("type")}
              >
                {Object.entries(TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="template-content">Conteúdo</Label>
              <textarea
                id="template-content"
                rows={6}
                className="w-full rounded border border-default bg-surface px-3 py-2 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                {...form.register("content")}
              />
            </div>
          </>
        )}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir modelo?"
        description={`"${pendingDelete?.name ?? ""}" vai para a lixeira — dá para restaurar depois.`}
        confirmLabel="Excluir"
        destructive
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

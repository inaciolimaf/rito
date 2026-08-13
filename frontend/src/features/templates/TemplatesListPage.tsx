import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import { TabBar } from "@/components/domain/TabBar";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useFilters } from "@/components/domain/useFilters";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  copyPublicTemplate,
  createTemplate,
  deleteTemplate,
  duplicateTemplate,
  listPublicTemplates,
  listTemplates,
  restoreTemplate,
  type PublicTemplateData,
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

const LIBRARY_TABS = [
  { value: "mine" as const, label: "Meus modelos" },
  { value: "public" as const, label: "Biblioteca Pública" },
];

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

const PUBLIC_FILTER_FIELDS: FilterFieldDef[] = [
  {
    key: "publicType",
    label: "Tipo",
    type: "select",
    options: [
      { value: "CONTRATO", label: "Contratos" },
      { value: "PETICAO", label: "Petições" },
      { value: "RECURSO", label: "Recursos" },
      { value: "DOCUMENTO", label: "Documentos" },
    ],
  },
];

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString("pt-BR");
}

function PublicTemplatesPanel(): JSX.Element {
  const navigate = useNavigate();
  const { values } = useFilters(PUBLIC_FILTER_FIELDS);
  const type =
    typeof values.publicType === "string" ? (values.publicType as TemplateType) : undefined;

  const { data, isLoading, error } = useQuery({
    queryKey: ["public-templates", type],
    queryFn: () => listPublicTemplates(type),
  });

  const copy = useMutation({
    mutationFn: (id: string) => copyPublicTemplate(id),
    onSuccess: (created) => navigate(`/library/${created.id}`),
  });

  const columns: DataTableColumn<PublicTemplateData>[] = [
    { id: "name", header: "Nome", cell: (row) => row.name },
    { id: "type", header: "Tipo", cell: (row) => TYPE_LABELS[row.type] },
  ];

  return (
    <div className="space-y-4">
      <FilterBar fields={PUBLIC_FILTER_FIELDS} />
      <DataTable
        columns={columns}
        data={data ?? []}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum modelo público desse tipo."
        rowActions={(row) => (
          <button
            type="button"
            className="text-sm text-accent underline"
            disabled={copy.isPending}
            onClick={() => copy.mutate(row.id)}
          >
            Copiar para meus modelos
          </button>
        )}
      />
    </div>
  );
}

/** Biblioteca de modelos (spec 064) — aqui só cadastro rápido (nome + tipo), busca,
 * filtro por tipo e lixeira. O conteúdo (spec 065) e as variáveis (spec 066) se
 * editam em `/library/:id`, pra onde "Novo modelo" e "Editar" levam. A 2ª aba
 * (spec 068) é o catálogo global — só copiar, sem editor aqui. */
export function TemplatesListPage(): JSX.Element {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const libraryTab = searchParams.get("tab") === "public" ? "public" : "mine";
  const { values } = useFilters(FILTER_FIELDS);
  const view = typeof values.view === "string" ? (values.view as TemplateView) : "all";
  const q = typeof values.q === "string" ? values.q : undefined;
  const isTrash = view === "trash";

  const { data, isLoading, error } = useQuery({
    queryKey: ["templates", { view, q }],
    queryFn: () => listTemplates({ view, q }),
    enabled: libraryTab === "mine",
  });

  const {
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    handleSubmit,
    handleConfirmDelete,
  } = useCrudResource<TemplateData, TemplateFormValues>({
    queryKey: ["templates"],
    create: async (formValues) => {
      const created = await createTemplate({ ...formValues, content: "" });
      navigate(`/library/${created.id}`);
      return created;
    },
    update: async () => {
      throw new Error("Edição acontece em /library/:id, não neste modal.");
    },
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
        {libraryTab === "mine" && <Button onClick={openCreateModal}>Novo modelo</Button>}
      </div>

      <TabBar
        items={LIBRARY_TABS}
        active={libraryTab}
        ariaLabel="Modelos do escritório ou biblioteca pública"
        onSelect={(value) => setSearchParams(value === "mine" ? {} : { tab: value })}
      />

      {libraryTab === "public" ? (
        <PublicTemplatesPanel />
      ) : (
        <>
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
                      onClick={() => navigate(`/library/${row.id}`)}
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
        </>
      )}

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title="Novo modelo"
        schema={templateFormSchema}
        defaultValues={DEFAULT_TEMPLATE_FORM_VALUES}
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

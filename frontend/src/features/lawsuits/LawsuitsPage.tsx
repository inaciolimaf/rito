import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { EmptyState } from "@/components/domain/EmptyState";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, EntityOption, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { Button } from "@/components/ui/button";
import { listCourts } from "@/features/courts/api";
import { listCustomers } from "@/features/customers/api";
import {
  addParty,
  createLawsuit,
  deleteLawsuit,
  exportLawsuits,
  getLawsuit,
  listLawsuits,
  listParties,
  removeParty,
  updateLawsuit,
  validateProcessNumber,
  type LawsuitData,
  type LawsuitFormPayload,
  type LawsuitListItem,
  type PartyData,
} from "@/features/lawsuits/api";
import { LastMovementCell, PartiesCell } from "@/features/lawsuits/LawsuitListCells";
import { FolderGroupView } from "@/features/lawsuits/FolderGroupView";
import { LawsuitForm } from "@/features/lawsuits/LawsuitForm";
import { LawsuitStatsPanel } from "@/features/lawsuits/LawsuitStatsPanel";
import type { PartyFormValue } from "@/features/lawsuits/PartySelector";
import { QuickViewSelect } from "@/features/lawsuits/QuickViewSelect";
import {
  DEFAULT_LAWSUIT_FORM_VALUES,
  lawsuitFormSchema,
  type LawsuitFormValues,
} from "@/features/lawsuits/schema";
import { listStages } from "@/features/stages/api";
import { getUser, listUsers } from "@/features/users/api";
import { formatCnj } from "@/lib/cnj";
import { ApiError } from "@/lib/errors";

function toPayload(values: LawsuitFormValues): LawsuitFormPayload {
  return {
    user_id: values.user_id,
    lawsuit_type_id: values.lawsuit_type_id,
    stage_id: values.stage_id,
    parties: values.parties.map((party) => ({
      customer_id: party.customer_id,
      pole: party.pole,
      is_client: party.is_client,
    })),
    court_id: values.court_id ? Number(values.court_id) : null,
    court_system_id: values.court_system_id ? Number(values.court_system_id) : null,
    process_number: values.process_number || null,
    protocol_number: values.protocol_number || null,
    originating_process: values.originating_process || null,
    folder: values.folder || null,
    filing_year: values.filing_year ? Number(values.filing_year) : null,
    judiciary: values.judiciary || null,
    county: values.county || null,
    court_division: values.court_division || null,
    process_date: values.process_date || null,
    notes: values.notes || null,
    case_value: values.case_value ? Number(values.case_value) : null,
    fees_value: values.fees_value ? Number(values.fees_value) : null,
    fees_percentage: values.fees_percentage ? Number(values.fees_percentage) : null,
    contingency: values.contingency || null,
    closure_date: values.closure_date || null,
    transit_date: values.transit_date || null,
    archived_date: values.archived_date || null,
    outcome: values.outcome || null,
  };
}

/** Decimal da API vem como número ("1234.56"); o campo mascarado guarda o cru com ponto. */
function decimalToRaw(value: number | null): string {
  return value != null ? value.toFixed(2) : "";
}

function toFormValues(lawsuit: LawsuitData, parties: PartyData[]): LawsuitFormValues {
  return {
    user_id: lawsuit.user_id,
    lawsuit_type_id: lawsuit.lawsuit_type_id,
    stage_id: lawsuit.stage_id,
    parties: parties.map((party) => ({
      customer_id: party.customer_id,
      label: party.customer_name,
      pole: party.pole,
      is_client: party.is_client,
    })),
    court_id: lawsuit.court_id != null ? String(lawsuit.court_id) : "",
    court_system_id: lawsuit.court_system_id != null ? String(lawsuit.court_system_id) : "",
    process_number: lawsuit.process_number ?? "",
    protocol_number: lawsuit.protocol_number ?? "",
    originating_process: lawsuit.originating_process ?? "",
    folder: lawsuit.folder ?? "",
    filing_year: lawsuit.filing_year != null ? String(lawsuit.filing_year) : "",
    judiciary: lawsuit.judiciary ?? "",
    county: lawsuit.county ?? "",
    court_division: lawsuit.court_division ?? "",
    process_date: lawsuit.process_date ?? "",
    notes: lawsuit.notes ?? "",
    case_value: decimalToRaw(lawsuit.case_value),
    fees_value: decimalToRaw(lawsuit.fees_value),
    fees_percentage: decimalToRaw(lawsuit.fees_percentage),
    contingency: lawsuit.contingency ?? "",
    closure_date: lawsuit.closure_date ?? "",
    transit_date: lawsuit.transit_date ?? "",
    archived_date: lawsuit.archived_date ?? "",
    outcome: lawsuit.outcome ?? "",
  };
}

/** Tela de trabalho do gestor (spec 027): 12 visões + filtros combináveis na URL +
 * DataTable. O detalhe (timeline) fica em /lawsuits/:id. */
export function LawsuitsPage(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();

  const { data: stagesPage } = useQuery({
    queryKey: ["stages", "for-lawsuit-list"],
    queryFn: () => listStages({}),
  });
  const stages = stagesPage?.items ?? [];

  const filterFields: FilterFieldDef[] = [
    { key: "q", label: "Buscar", type: "text" },
    {
      key: "stage_id",
      label: "Etapa",
      type: "multiselect",
      options: stages.map((stage) => ({ value: stage.id, label: stage.name })),
    },
    {
      key: "customer_type",
      label: "Tipo de pessoa",
      type: "select",
      options: [
        { value: "PF", label: "Pessoa física" },
        { value: "PJ", label: "Pessoa jurídica" },
      ],
    },
    { key: "created_from", label: "Cadastro de", type: "date" },
    { key: "created_to", label: "Cadastro até", type: "date" },
    { key: "archived", label: "Arquivados", type: "boolean" },
  ];

  const { values } = useFilters(filterFields);
  const view = searchParams.get("view") ?? "all";
  const groupBy = searchParams.get("group_by");
  const folder = searchParams.get("folder") ?? undefined;
  const q = typeof values.q === "string" ? values.q : undefined;
  const stageId = Array.isArray(values.stage_id)
    ? values.stage_id.join(",")
    : typeof values.stage_id === "string"
      ? values.stage_id
      : undefined;
  const customerType = typeof values.customer_type === "string" ? values.customer_type : undefined;
  const createdFrom = typeof values.created_from === "string" ? values.created_from : undefined;
  const createdTo = typeof values.created_to === "string" ? values.created_to : undefined;
  const archived = values.archived === "true" ? true : undefined;

  const [cursorStack, setCursorStack] = React.useState<string[]>([]);
  const currentCursor = cursorStack[cursorStack.length - 1];

  const activeFilters = {
    view,
    q,
    stage_id: stageId,
    customer_type: customerType,
    created_from: createdFrom,
    created_to: createdTo,
    archived,
    folder,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["lawsuits-list", activeFilters, currentCursor],
    queryFn: () => listLawsuits({ ...activeFilters, cursor: currentCursor, limit: 20 }),
  });

  React.useEffect(() => {
    setCursorStack([]);
  }, [view, q, stageId, customerType, createdFrom, createdTo, archived, folder]);

  // ---- modal de criar/editar (mesmo fluxo das specs 022–025) ----
  const [modalOpen, setModalOpen] = React.useState(false);
  const [formError, setFormError] = React.useState<ApiError | null>(null);
  const [editingLawsuit, setEditingLawsuit] = React.useState<LawsuitData | null>(null);
  const [editingParties, setEditingParties] = React.useState<PartyData[]>([]);
  const [pendingDelete, setPendingDelete] = React.useState<LawsuitListItem | null>(null);

  const { data: courts = [] } = useQuery({
    queryKey: ["courts", "for-lawsuit-form"],
    queryFn: () => listCourts({}),
  });

  const { data: responsible = null } = useQuery({
    queryKey: ["users", editingLawsuit?.user_id],
    queryFn: () => getUser(editingLawsuit!.user_id),
    enabled: !!editingLawsuit,
  });

  async function searchUsers(query: string): Promise<EntityOption[]> {
    const page = await listUsers({ q: query, limit: 20 });
    return page.items.map((item) => ({ id: item.id, label: item.name }));
  }

  async function searchCustomers(query: string): Promise<EntityOption[]> {
    const page = await listCustomers({ q: query, limit: 20 });
    return page.items.map((item) => ({ id: item.id, label: item.name }));
  }

  function openCreateModal(): void {
    setEditingLawsuit(null);
    setEditingParties([]);
    setFormError(null);
    setModalOpen(true);
  }

  async function openEditModal(item: LawsuitListItem): Promise<void> {
    const fresh = await getLawsuit(item.id);
    setEditingLawsuit(fresh);
    setEditingParties(await listParties(fresh.id));
    setFormError(null);
    setModalOpen(true);
  }

  /** PUT do processo não aceita `parties` (spec 023 §5) — na edição, as partes são
   * sincronizadas pelos endpoints dedicados: primeiro as adições (para nunca ficar sem
   * nenhuma parte, regra 1), depois as remoções. */
  async function syncParties(lawsuitId: string, next: PartyFormValue[]): Promise<void> {
    const keyOf = (party: { customer_id: string; pole: string }): string =>
      `${party.customer_id}:${party.pole}`;
    const nextKeys = new Set(next.map(keyOf));
    const initialKeys = new Set(editingParties.map(keyOf));
    for (const party of next) {
      if (!initialKeys.has(keyOf(party))) {
        await addParty(lawsuitId, {
          customer_id: party.customer_id,
          pole: party.pole,
          is_client: party.is_client,
        });
      }
    }
    for (const party of editingParties) {
      if (!nextKeys.has(keyOf(party))) {
        await removeParty(lawsuitId, party.id);
      }
    }
  }

  async function handleSubmit(formValues: LawsuitFormValues): Promise<void> {
    setFormError(null);
    try {
      const payload = toPayload(formValues);
      if (editingLawsuit) {
        // PUT não aceita `parties` (spec 023 §5) — partes vão pelos endpoints dedicados.
        const updatePayload = { ...payload };
        delete updatePayload.parties;
        await updateLawsuit(editingLawsuit.id, updatePayload);
        await syncParties(editingLawsuit.id, formValues.parties);
      } else {
        await createLawsuit(payload);
      }
      setModalOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["lawsuits-list"] });
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  async function handleConfirmDelete(): Promise<void> {
    if (!pendingDelete) return;
    await deleteLawsuit(pendingDelete.id);
    setPendingDelete(null);
    await queryClient.invalidateQueries({ queryKey: ["lawsuits-list"] });
  }

  const currentResponsible: EntityOption | null = responsible
    ? { id: responsible.id, label: responsible.name }
    : null;

  const currentCourt: EntityOption | null =
    editingLawsuit?.court_id != null
      ? (() => {
          const found = courts.find((court) => court.id === editingLawsuit.court_id);
          return found ? { id: String(found.id), label: `${found.code} — ${found.name}` } : null;
        })()
      : null;

  const columns: DataTableColumn<LawsuitListItem>[] = [
    {
      id: "parties",
      header: "Partes",
      cell: (row) => <PartiesCell parties={row.parties} partiesTotal={row.parties_total} />,
    },
    { id: "type", header: "Tipo de ação", cell: (row) => row.lawsuit_type_name },
    {
      id: "number",
      header: "Número do processo",
      cell: (row) =>
        row.process_number ? (
          <Link
            to={`/lawsuits/${row.id}`}
            className="text-accent underline"
            onClick={(event) => event.stopPropagation()}
          >
            {formatCnj(row.process_number)}
          </Link>
        ) : (
          (row.folder ?? "—")
        ),
    },
    {
      id: "created_at",
      header: "Data cadastro",
      cell: (row) => new Date(row.created_at).toLocaleDateString("pt-BR"),
    },
    {
      id: "last_movement",
      header: "Último andamento",
      cell: (row) => row.last_movement_title ?? <span className="text-muted">—</span>,
    },
    {
      id: "last_movement_at",
      header: "Data andamento",
      cell: (row) => <LastMovementCell occurredAt={row.last_movement_at} />,
    },
  ];

  const items = data?.items ?? [];
  const hasActiveFilters =
    view !== "all" ||
    [q, stageId, customerType, createdFrom, createdTo, folder].some((v) => v != null && v !== "") ||
    archived === true;

  function toggleGroupBy(): void {
    const next = new URLSearchParams(searchParams);
    if (groupBy === "folder") {
      next.delete("group_by");
    } else {
      next.set("group_by", "folder");
    }
    navigate(`/lawsuits?${next.toString()}`);
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold text-primary">Processos</h1>
          <QuickViewSelect />
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={toggleGroupBy}>
            {groupBy === "folder" ? "Ver lista" : "Agrupar por pasta"}
          </Button>
          <Button variant="outline" onClick={() => void exportLawsuits("xlsx", activeFilters)}>
            Exportar XLSX
          </Button>
          <Button variant="outline" onClick={() => void exportLawsuits("pdf", activeFilters)}>
            Exportar PDF
          </Button>
          <Button onClick={openCreateModal}>Novo processo</Button>
        </div>
      </div>

      <FilterBar fields={filterFields} />

      <LawsuitStatsPanel />

      {groupBy === "folder" ? (
        <FolderGroupView />
      ) : items.length === 0 && !isLoading && !hasActiveFilters ? (
        <EmptyState
          title="Nenhum processo cadastrado ainda"
          description="Cadastre o primeiro processo do escritório."
          action={{ label: "Novo processo", onClick: openCreateModal }}
        />
      ) : (
        <DataTable
          columns={columns}
          data={items}
          getRowId={(row) => row.id}
          isLoading={isLoading}
          error={error instanceof ApiError ? error.message : null}
          emptyMessage="Nenhum processo encontrado com esses filtros."
          rowActions={(row) => (
            <div className="flex gap-2">
              <button
                type="button"
                className="text-sm text-accent underline"
                onClick={() => navigate(`/lawsuits/${row.id}`)}
              >
                Abrir
              </button>
              <button
                type="button"
                className="text-sm text-accent underline"
                onClick={() => void openEditModal(row)}
              >
                Editar
              </button>
              {!row.is_archived && (
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
      )}

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingLawsuit ? "Editar processo" : "Novo processo"}
        schema={lawsuitFormSchema}
        defaultValues={
          editingLawsuit
            ? toFormValues(editingLawsuit, editingParties)
            : DEFAULT_LAWSUIT_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <LawsuitForm
            form={form}
            onSearchUsers={searchUsers}
            onSearchCustomers={searchCustomers}
            onValidateProcessNumber={validateProcessNumber}
            currentResponsible={currentResponsible}
            currentCourt={currentCourt}
            initialGroupId={editingLawsuit?.action_group_id}
            initialStepId={editingLawsuit?.step_id}
          />
        )}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir processo?"
        description="O processo será arquivado — dados ficam preservados, mas ele deixa de aparecer nas listagens ativas."
        confirmLabel="Excluir"
        destructive
        onConfirm={() => void handleConfirmDelete()}
      />
    </div>
  );
}

import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { EmptyState } from "@/components/domain/EmptyState";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, EntityOption, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { Button } from "@/components/ui/button";
import { listCustomerOrigins } from "@/features/customer-origins/api";
import {
  archiveCustomer,
  createCustomer,
  exportCustomers,
  getCustomer,
  listCustomers,
  listMaritalStatuses,
  updateCustomer,
  uploadCustomerPhoto,
  type CustomerData,
  type CustomerFormPayload,
  type CustomerListItem,
} from "@/features/customers/api";
import { BirthdayBadge } from "@/features/customers/BirthdayBadge";
import { CustomerForm } from "@/features/customers/CustomerForm";
import { CustomerStatsPanel } from "@/features/customers/CustomerStatsPanel";
import { PhotoUploader } from "@/features/customers/PhotoUploader";
import {
  customerFormSchema,
  DEFAULT_CUSTOMER_FORM_VALUES,
  type CustomerFormValues,
} from "@/features/customers/schema";
import { listStates } from "@/features/locations/api";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

function toPayload(values: CustomerFormValues): CustomerFormPayload {
  return {
    type: values.type,
    name: values.name,
    origin_id: values.origin_id,
    identification: values.identification || null,
    document: values.document || null,
    notes: values.notes || null,
    birthdate: values.birthdate || null,
    marital_status_id: values.marital_status_id ? Number(values.marital_status_id) : null,
    occupation: values.occupation || null,
    gender: (values.gender || null) as "F" | "M" | null,
    nationality: values.nationality || null,
    mother_name: values.mother_name || null,
    cellphone: values.cellphone || null,
    phone: values.phone || null,
    email: values.email || null,
    country: values.country,
    postal_code: values.postal_code || null,
    state: values.state || null,
    city: values.city || null,
    street: values.street || null,
    region: values.region || null,
    number_pis: values.number_pis || null,
    number_ctps: values.number_ctps || null,
    number_cid: values.number_cid || null,
    has_representative: values.has_representative,
    rep_name: values.rep_name || null,
    rep_identification: values.rep_identification || null,
    rep_document: values.rep_document || null,
    rep_birthdate: values.rep_birthdate || null,
    rep_country: values.rep_country || null,
    rep_state: values.rep_state || null,
    rep_city: values.rep_city || null,
    rep_street: values.rep_street || null,
    rep_region: values.rep_region || null,
    rep_postal_code: values.rep_postal_code || null,
  };
}

function toFormValues(customer: CustomerData): CustomerFormValues {
  return {
    type: customer.type,
    name: customer.name,
    origin_id: customer.origin_id,
    identification: customer.identification ?? "",
    document: customer.document ?? "",
    notes: customer.notes ?? "",
    birthdate: customer.birthdate ?? "",
    marital_status_id: customer.marital_status_id ? String(customer.marital_status_id) : "",
    occupation: customer.occupation ?? "",
    gender: (customer.gender ?? "") as "F" | "M" | "",
    nationality: customer.nationality ?? "",
    mother_name: customer.mother_name ?? "",
    cellphone: customer.cellphone ?? "",
    phone: customer.phone ?? "",
    email: customer.email ?? "",
    country: customer.country,
    postal_code: customer.postal_code ?? "",
    state: customer.state ?? "",
    city: customer.city ?? "",
    street: customer.street ?? "",
    region: customer.region ?? "",
    number_pis: customer.number_pis ?? "",
    number_ctps: customer.number_ctps ?? "",
    number_cid: customer.number_cid ?? "",
    has_representative: customer.has_representative,
    rep_name: customer.rep_name ?? "",
    rep_identification: customer.rep_identification ?? "",
    rep_document: customer.rep_document ?? "",
    rep_birthdate: customer.rep_birthdate ?? "",
    rep_country: customer.rep_country ?? "",
    rep_state: customer.rep_state ?? "",
    rep_city: customer.rep_city ?? "",
    rep_street: customer.rep_street ?? "",
    rep_region: customer.rep_region ?? "",
    rep_postal_code: customer.rep_postal_code ?? "",
  };
}

/** Primeira tela completa do sistema (spec 019): listagem + dashboard, prova de que o
 * design system da spec 007 funciona de ponta a ponta. */
export function CustomerListPage(): JSX.Element {
  const { user } = useAuth();
  const canArchive = user?.role === "GESTOR" || user?.role === "ADMINISTRADOR";
  const queryClient = useQueryClient();

  const { data: statesData = [] } = useQuery({ queryKey: ["states"], queryFn: listStates });
  const { data: originsPage } = useQuery({
    queryKey: ["customer-origins", "for-customer-list"],
    queryFn: () => listCustomerOrigins({}),
  });
  const origins = originsPage?.items ?? [];

  const filterFields: FilterFieldDef[] = [
    { key: "q", label: "Buscar", type: "text" },
    {
      key: "type",
      label: "Tipo",
      type: "select",
      options: [
        { value: "PF", label: "Pessoa física" },
        { value: "PJ", label: "Pessoa jurídica" },
      ],
    },
    {
      key: "state",
      label: "Estado",
      type: "select",
      options: statesData.map((state) => ({ value: state.code, label: state.name })),
    },
    { key: "city", label: "Cidade", type: "text" },
    {
      key: "origin_id",
      label: "Origem",
      type: "select",
      options: origins.map((origin) => ({ value: origin.id, label: origin.name })),
    },
    {
      key: "birthdays",
      label: "Aniversariantes",
      type: "select",
      options: [
        { value: "day", label: "Do dia" },
        { value: "month", label: "Do mês" },
      ],
    },
    { key: "created_from", label: "Cadastro de", type: "date" },
    { key: "created_to", label: "Cadastro até", type: "date" },
    { key: "archived", label: "Arquivados", type: "boolean" },
  ];

  const { values } = useFilters(filterFields);
  const q = typeof values.q === "string" ? values.q : undefined;
  const type = typeof values.type === "string" ? (values.type as "PF" | "PJ") : undefined;
  const state = typeof values.state === "string" ? values.state : undefined;
  const city = typeof values.city === "string" ? values.city : undefined;
  const originId = typeof values.origin_id === "string" ? values.origin_id : undefined;
  const birthdays =
    typeof values.birthdays === "string" ? (values.birthdays as "day" | "month") : undefined;
  const createdFrom = typeof values.created_from === "string" ? values.created_from : undefined;
  const createdTo = typeof values.created_to === "string" ? values.created_to : undefined;
  const archived = values.archived === "true";

  const [cursorStack, setCursorStack] = React.useState<string[]>([]);
  const currentCursor = cursorStack[cursorStack.length - 1];

  const filters = {
    q,
    type,
    state,
    city,
    origin_id: originId,
    birthdays,
    created_from: createdFrom,
    created_to: createdTo,
    archived,
  };

  const { data, isLoading, error } = useQuery({
    queryKey: ["customers", filters, currentCursor],
    queryFn: () => listCustomers({ ...filters, cursor: currentCursor, limit: 20 }),
  });

  React.useEffect(() => {
    setCursorStack([]);
  }, [q, type, state, city, originId, birthdays, createdFrom, createdTo, archived]);

  const [editingCustomer, setEditingCustomer] = React.useState<CustomerData | null>(null);
  const [modalOpen, setModalOpen] = React.useState(false);
  const [formError, setFormError] = React.useState<ApiError | null>(null);
  const [pendingArchive, setPendingArchive] = React.useState<CustomerListItem | null>(null);

  async function searchOrigins(query: string): Promise<EntityOption[]> {
    const page = await listCustomerOrigins({ q: query });
    return page.items.map((item) => ({ id: item.id, label: item.name }));
  }

  function openCreateModal(): void {
    setEditingCustomer(null);
    setFormError(null);
    setModalOpen(true);
  }

  async function openEditModal(item: CustomerListItem): Promise<void> {
    const fresh = await getCustomer(item.id);
    setEditingCustomer(fresh);
    setFormError(null);
    setModalOpen(true);
  }

  async function handleSubmit(formValues: CustomerFormValues): Promise<void> {
    setFormError(null);
    try {
      const payload = toPayload(formValues);
      if (editingCustomer) {
        const updated = await updateCustomer(editingCustomer.id, payload);
        setEditingCustomer(updated);
      } else {
        await createCustomer(payload);
      }
      setModalOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["customers"] });
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  async function handleUploadPhoto(file: File): Promise<void> {
    if (!editingCustomer) return;
    const updated = await uploadCustomerPhoto(editingCustomer.id, file);
    setEditingCustomer(updated);
  }

  async function handleConfirmArchive(): Promise<void> {
    if (!pendingArchive) return;
    await archiveCustomer(pendingArchive.id);
    setPendingArchive(null);
    await queryClient.invalidateQueries({ queryKey: ["customers"] });
  }

  const currentOrigin: EntityOption | null = editingCustomer
    ? (() => {
        const found = origins.find((item) => item.id === editingCustomer.origin_id);
        return found ? { id: found.id, label: found.name } : null;
      })()
    : null;

  const { data: maritalStatuses = [] } = useQuery({
    queryKey: ["marital-statuses"],
    queryFn: listMaritalStatuses,
  });

  const columns: DataTableColumn<CustomerListItem>[] = [
    {
      id: "name",
      header: "Nome do cliente",
      cell: (row) => (
        <span className="flex items-center gap-1">
          {row.name}
          <BirthdayBadge birthdate={row.birthdate} />
        </span>
      ),
    },
    {
      id: "cellphone",
      header: "Celular",
      cell: (row) =>
        row.whatsapp_link ? (
          <a
            href={row.whatsapp_link}
            target="_blank"
            rel="noreferrer"
            className="text-accent underline"
          >
            {row.cellphone}
          </a>
        ) : (
          "—"
        ),
    },
    { id: "city", header: "Cidade", cell: (row) => row.city ?? "—" },
    {
      id: "created_at",
      header: "Data do cadastro",
      cell: (row) => new Date(row.created_at).toLocaleDateString("pt-BR"),
    },
  ];

  const items = data?.items ?? [];
  const hasActiveFilters = Object.values(filters).some(
    (value) => value !== undefined && value !== false,
  );

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Contatos</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void exportCustomers("xlsx", filters)}>
            Exportar XLSX
          </Button>
          <Button variant="outline" onClick={() => void exportCustomers("pdf", filters)}>
            Exportar PDF
          </Button>
          <Button onClick={openCreateModal}>Novo contato</Button>
        </div>
      </div>

      <CustomerStatsPanel />

      <FilterBar fields={filterFields} />

      {items.length === 0 && !isLoading && !hasActiveFilters ? (
        <EmptyState
          title="Nenhum contato cadastrado ainda"
          description="Cadastre o primeiro cliente ou parte contrária do escritório."
          action={{ label: "Novo contato", onClick: openCreateModal }}
        />
      ) : (
        <DataTable
          columns={columns}
          data={items}
          getRowId={(row) => row.id}
          isLoading={isLoading}
          error={error instanceof ApiError ? error.message : null}
          emptyMessage="Nenhum contato encontrado com esses filtros."
          rowActions={(row) => (
            <div className="flex gap-2">
              <button
                type="button"
                className="text-sm text-accent underline"
                onClick={() => void openEditModal(row)}
              >
                Editar
              </button>
              {!row.is_archived && canArchive && (
                <button
                  type="button"
                  className="text-sm text-danger underline"
                  onClick={() => setPendingArchive(row)}
                >
                  Arquivar
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
        title={editingCustomer ? "Editar contato" : "Novo contato"}
        schema={customerFormSchema}
        defaultValues={
          editingCustomer ? toFormValues(editingCustomer) : DEFAULT_CUSTOMER_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <>
            <CustomerForm
              form={form}
              maritalStatuses={maritalStatuses}
              onSearchOrigins={searchOrigins}
              currentOrigin={currentOrigin}
            />
            {editingCustomer && (
              <PhotoUploader photoUrl={editingCustomer.photo_url} onUpload={handleUploadPhoto} />
            )}
          </>
        )}
      </FormModal>

      <ConfirmDialog
        open={pendingArchive !== null}
        onOpenChange={(open) => {
          if (!open) setPendingArchive(null);
        }}
        title="Arquivar contato?"
        description={`"${pendingArchive?.name ?? ""}" será arquivado — o histórico permanece (regra 5).`}
        confirmLabel="Arquivar"
        destructive
        onConfirm={handleConfirmArchive}
      />
    </div>
  );
}

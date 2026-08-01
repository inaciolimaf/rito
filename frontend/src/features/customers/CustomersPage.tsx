import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import type { EntityOption } from "@/components/domain/types";
import { FormModal } from "@/components/domain/FormModal";
import { Button } from "@/components/ui/button";
import {
  createCustomer,
  getCustomer,
  updateCustomer,
  uploadCustomerPhoto,
  type CustomerData,
  type CustomerFormPayload,
  listMaritalStatuses,
} from "@/features/customers/api";
import { CustomerForm } from "@/features/customers/CustomerForm";
import { PhotoUploader } from "@/features/customers/PhotoUploader";
import {
  customerFormSchema,
  DEFAULT_CUSTOMER_FORM_VALUES,
  type CustomerFormValues,
} from "@/features/customers/schema";
import { listCustomerOrigins } from "@/features/customer-origins/api";
import { ApiError } from "@/lib/errors";

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

/** Listagem/filtros/dashboard de Contatos são a spec 019 — esta tela cobre só o modal de
 * criação/edição (spec 017, seção 6: "Rota: modal sobre /customers"). */
export function CustomersPage(): JSX.Element {
  const [modalOpen, setModalOpen] = React.useState(false);
  const [formError, setFormError] = React.useState<ApiError | null>(null);
  const [lastCustomer, setLastCustomer] = React.useState<CustomerData | null>(null);

  const { data: maritalStatuses = [] } = useQuery({
    queryKey: ["marital-statuses"],
    queryFn: listMaritalStatuses,
  });

  const { data: originsPage } = useQuery({
    queryKey: ["customer-origins", "for-customer-form"],
    queryFn: () => listCustomerOrigins({}),
  });
  const origins = originsPage?.items ?? [];

  async function searchOrigins(query: string): Promise<EntityOption[]> {
    const page = await listCustomerOrigins({ q: query });
    return page.items.map((item) => ({ id: item.id, label: item.name }));
  }

  function openCreateModal(): void {
    setFormError(null);
    setModalOpen(true);
  }

  async function handleSubmit(values: CustomerFormValues): Promise<void> {
    setFormError(null);
    try {
      const payload = toPayload(values);
      const saved = lastCustomer
        ? await updateCustomer(lastCustomer.id, payload)
        : await createCustomer(payload);
      setLastCustomer(saved);
      setModalOpen(false);
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  async function handleUploadPhoto(file: File): Promise<void> {
    if (!lastCustomer) return;
    const updated = await uploadCustomerPhoto(lastCustomer.id, file);
    setLastCustomer(updated);
  }

  async function openEditModal(): Promise<void> {
    if (!lastCustomer) return;
    const fresh = await getCustomer(lastCustomer.id);
    setLastCustomer(fresh);
    setFormError(null);
    setModalOpen(true);
  }

  const currentOrigin: EntityOption | null = lastCustomer
    ? (() => {
        const found = origins.find((item) => item.id === lastCustomer.origin_id);
        return found ? { id: found.id, label: found.name } : null;
      })()
    : null;

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Contatos</h1>
        <Button onClick={openCreateModal}>Novo contato</Button>
      </div>

      {lastCustomer ? (
        <div className="space-y-3 rounded border border-default bg-surface p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-primary">{lastCustomer.name}</p>
              <p className="text-sm text-muted">
                {lastCustomer.type === "PF" ? "Pessoa física" : "Pessoa jurídica"}
              </p>
            </div>
            <button
              type="button"
              className="text-sm text-accent underline"
              onClick={() => void openEditModal()}
            >
              Editar
            </button>
          </div>
          <PhotoUploader photoUrl={lastCustomer.photo_url} onUpload={handleUploadPhoto} />
        </div>
      ) : (
        <p className="text-sm text-muted">Nenhum contato criado ainda nesta sessão.</p>
      )}

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={lastCustomer ? "Editar contato" : "Novo contato"}
        schema={customerFormSchema}
        defaultValues={lastCustomer ? toFormValues(lastCustomer) : DEFAULT_CUSTOMER_FORM_VALUES}
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <CustomerForm
            form={form}
            maritalStatuses={maritalStatuses}
            onSearchOrigins={searchOrigins}
            currentOrigin={currentOrigin}
          />
        )}
      </FormModal>
    </div>
  );
}

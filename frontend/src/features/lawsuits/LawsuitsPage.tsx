import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { FormModal } from "@/components/domain/FormModal";
import type { EntityOption } from "@/components/domain/types";
import { Button } from "@/components/ui/button";
import { listCourts } from "@/features/courts/api";
import { listCustomers } from "@/features/customers/api";
import {
  addParty,
  createLawsuit,
  deleteLawsuit,
  getLawsuit,
  listParties,
  removeParty,
  updateLawsuit,
  type LawsuitData,
  type LawsuitFormPayload,
  type PartyData,
} from "@/features/lawsuits/api";
import { LawsuitForm } from "@/features/lawsuits/LawsuitForm";
import type { PartyFormValue } from "@/features/lawsuits/PartySelector";
import {
  DEFAULT_LAWSUIT_FORM_VALUES,
  lawsuitFormSchema,
  type LawsuitFormValues,
} from "@/features/lawsuits/schema";
import { getUser, listUsers } from "@/features/users/api";
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
  };
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
  };
}

/** Listagem/filtros de Processos são a spec 027 — esta tela cobre só o modal de
 * criação/edição (spec 022 §6: "Rota: modal sobre /lawsuits"), mesmo padrão que
 * `CustomersPage` cobriu antes da listagem da spec 019 chegar. */
export function LawsuitsPage(): JSX.Element {
  const [modalOpen, setModalOpen] = React.useState(false);
  const [formError, setFormError] = React.useState<ApiError | null>(null);
  const [lastLawsuit, setLastLawsuit] = React.useState<LawsuitData | null>(null);
  const [lastParties, setLastParties] = React.useState<PartyData[]>([]);
  const [pendingDelete, setPendingDelete] = React.useState(false);

  const { data: courts = [] } = useQuery({
    queryKey: ["courts", "for-lawsuit-form"],
    queryFn: () => listCourts({}),
  });

  const { data: responsible = null } = useQuery({
    queryKey: ["users", lastLawsuit?.user_id],
    queryFn: () => getUser(lastLawsuit!.user_id),
    enabled: !!lastLawsuit,
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
    setFormError(null);
    setModalOpen(true);
  }

  async function openEditModal(): Promise<void> {
    if (!lastLawsuit) return;
    const fresh = await getLawsuit(lastLawsuit.id);
    setLastLawsuit(fresh);
    setLastParties(await listParties(fresh.id));
    setFormError(null);
    setModalOpen(true);
  }

  /** PUT do processo não aceita `parties` (spec 023 §5) — na edição, as partes são
   * sincronizadas pelos endpoints dedicados: primeiro as adições (para nunca ficar sem
   * nenhuma parte, regra 1), depois as remoções. A chave de comparação é
   * customer_id + polo (regra 2). */
  async function syncParties(lawsuitId: string, next: PartyFormValue[]): Promise<void> {
    const keyOf = (party: { customer_id: string; pole: string }): string =>
      `${party.customer_id}:${party.pole}`;
    const nextKeys = new Set(next.map(keyOf));
    const initialKeys = new Set(lastParties.map(keyOf));
    for (const party of next) {
      if (!initialKeys.has(keyOf(party))) {
        await addParty(lawsuitId, {
          customer_id: party.customer_id,
          pole: party.pole,
          is_client: party.is_client,
        });
      }
    }
    for (const party of lastParties) {
      if (!nextKeys.has(keyOf(party))) {
        await removeParty(lawsuitId, party.id);
      }
    }
    setLastParties(await listParties(lawsuitId));
  }

  async function handleSubmit(values: LawsuitFormValues): Promise<void> {
    setFormError(null);
    try {
      const payload = toPayload(values);
      let saved: LawsuitData;
      if (lastLawsuit) {
        // PUT não aceita `parties` (spec 023 §5) — partes vão pelos endpoints dedicados.
        const updatePayload = { ...payload };
        delete updatePayload.parties;
        saved = await updateLawsuit(lastLawsuit.id, updatePayload);
        await syncParties(saved.id, values.parties);
      } else {
        saved = await createLawsuit(payload);
        setLastParties(await listParties(saved.id));
      }
      setLastLawsuit(saved);
      setModalOpen(false);
    } catch (submitError) {
      setFormError(submitError instanceof ApiError ? submitError : null);
      throw submitError;
    }
  }

  async function handleConfirmDelete(): Promise<void> {
    if (!lastLawsuit) return;
    await deleteLawsuit(lastLawsuit.id);
    setLastLawsuit(await getLawsuit(lastLawsuit.id));
    setPendingDelete(false);
  }

  const currentResponsible: EntityOption | null = responsible
    ? { id: responsible.id, label: responsible.name }
    : null;

  const currentCourt: EntityOption | null =
    lastLawsuit?.court_id != null
      ? (() => {
          const found = courts.find((court) => court.id === lastLawsuit.court_id);
          return found ? { id: String(found.id), label: `${found.code} — ${found.name}` } : null;
        })()
      : null;

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Processos</h1>
        <Button onClick={openCreateModal}>Novo processo</Button>
      </div>

      {lastLawsuit ? (
        <div className="space-y-3 rounded border border-default bg-surface p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-primary">
                {lastLawsuit.process_number || lastLawsuit.folder || "Processo sem número"}
              </p>
              <p className="text-sm text-muted">
                {lastLawsuit.action_group_name} · {lastLawsuit.step_name}
                {lastLawsuit.is_archived ? " · Arquivado" : ""}
              </p>
            </div>
            <div className="flex gap-3">
              <button
                type="button"
                className="text-sm text-accent underline"
                onClick={() => void openEditModal()}
              >
                Editar
              </button>
              {!lastLawsuit.is_archived && (
                <button
                  type="button"
                  className="text-sm text-danger underline"
                  onClick={() => setPendingDelete(true)}
                >
                  Excluir
                </button>
              )}
            </div>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted">Nenhum processo criado ainda nesta sessão.</p>
      )}

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={lastLawsuit ? "Editar processo" : "Novo processo"}
        schema={lawsuitFormSchema}
        defaultValues={
          lastLawsuit ? toFormValues(lastLawsuit, lastParties) : DEFAULT_LAWSUIT_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <LawsuitForm
            form={form}
            onSearchUsers={searchUsers}
            onSearchCustomers={searchCustomers}
            currentResponsible={currentResponsible}
            currentCourt={currentCourt}
            initialGroupId={lastLawsuit?.action_group_id}
            initialStepId={lastLawsuit?.step_id}
          />
        )}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete}
        onOpenChange={setPendingDelete}
        title="Excluir processo?"
        description="O processo será arquivado — dados ficam preservados, mas ele deixa de aparecer nas listagens ativas."
        confirmLabel="Excluir"
        destructive
        onConfirm={() => void handleConfirmDelete()}
      />
    </div>
  );
}

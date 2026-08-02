import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { FormModal } from "@/components/domain/FormModal";
import type { EntityOption } from "@/components/domain/types";
import { Button } from "@/components/ui/button";
import { listCourts } from "@/features/courts/api";
import {
  createLawsuit,
  deleteLawsuit,
  getLawsuit,
  updateLawsuit,
  type LawsuitData,
  type LawsuitFormPayload,
} from "@/features/lawsuits/api";
import { LawsuitForm } from "@/features/lawsuits/LawsuitForm";
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

function toFormValues(lawsuit: LawsuitData): LawsuitFormValues {
  return {
    user_id: lawsuit.user_id,
    lawsuit_type_id: lawsuit.lawsuit_type_id,
    stage_id: lawsuit.stage_id,
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

  function openCreateModal(): void {
    setFormError(null);
    setModalOpen(true);
  }

  async function openEditModal(): Promise<void> {
    if (!lastLawsuit) return;
    const fresh = await getLawsuit(lastLawsuit.id);
    setLastLawsuit(fresh);
    setFormError(null);
    setModalOpen(true);
  }

  async function handleSubmit(values: LawsuitFormValues): Promise<void> {
    setFormError(null);
    try {
      const payload = toPayload(values);
      const saved = lastLawsuit
        ? await updateLawsuit(lastLawsuit.id, payload)
        : await createLawsuit(payload);
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
        defaultValues={lastLawsuit ? toFormValues(lastLawsuit) : DEFAULT_LAWSUIT_FORM_VALUES}
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <LawsuitForm
            form={form}
            onSearchUsers={searchUsers}
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

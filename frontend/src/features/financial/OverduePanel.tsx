import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import { StatCard } from "@/components/domain/StatCard";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useFilters } from "@/components/domain/useFilters";
import { AgingChart } from "@/features/financial/AgingChart";
import {
  getOverdueSummary,
  listOverdue,
  sendDunning,
  type AgingBucket,
  type OverdueTransactionData,
} from "@/features/financial/dunning-api";
import { DunningHistoryDrawer } from "@/features/financial/DunningHistoryDrawer";
import { DunningRulesForm } from "@/features/financial/DunningRulesForm";
import {
  DEFAULT_SEND_DUNNING_FORM_VALUES,
  sendDunningFormSchema,
  type SendDunningFormValues,
} from "@/features/financial/schema";
import { TemplateEditor } from "@/features/financial/TemplateEditor";
import { formatBrl } from "@/lib/money";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

const AGING_FILTER_FIELDS: FilterFieldDef[] = [
  {
    key: "aging",
    label: "Faixa de atraso",
    type: "select",
    options: [
      { value: "1-15", label: "1–15 dias" },
      { value: "16-30", label: "16–30 dias" },
      { value: "31-60", label: "31–60 dias" },
      { value: "61-90", label: "61–90 dias" },
      { value: "90+", label: "90+ dias" },
    ],
  },
];

function formatDate(value: string): string {
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

/** Painel de inadimplência (spec 061) — atrasados com aging, resumo, envio manual de
 * cobrança e histórico por lançamento. `DunningRulesForm` (a régua automática) fica na
 * mesma aba: configurar e acompanhar cobrança são a mesma tarefa para quem usa isto. */
export function OverduePanel(): JSX.Element {
  const { user } = useAuth();
  const canSend = user?.financialAccess === "FULL";
  const queryClient = useQueryClient();

  const { values } = useFilters(AGING_FILTER_FIELDS);
  const aging = typeof values.aging === "string" ? (values.aging as AgingBucket) : undefined;

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ["overdue", "summary"],
    queryFn: () => getOverdueSummary(),
  });

  const {
    data: overdueList,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["overdue", { aging }],
    queryFn: () => listOverdue({ aging }),
  });
  const overdueRows = overdueList?.items ?? [];

  const [sendingFor, setSendingFor] = React.useState<OverdueTransactionData | null>(null);
  const [sendError, setSendError] = React.useState<ApiError | null>(null);
  const [historyFor, setHistoryFor] = React.useState<OverdueTransactionData | null>(null);

  const send = useMutation({
    mutationFn: (values: SendDunningFormValues) => {
      if (!sendingFor) throw new Error("Nenhum lançamento selecionado.");
      return sendDunning(sendingFor.id, values);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dunning-attempts", sendingFor?.id] });
      setSendError(null);
      setSendingFor(null);
    },
    onError: (mutationError: unknown) => {
      setSendError(mutationError instanceof ApiError ? mutationError : null);
    },
  });

  const columns: DataTableColumn<OverdueTransactionData>[] = [
    { id: "customer_name", header: "Cliente", cell: (row) => row.customer_name ?? "—" },
    { id: "process_number", header: "Processo", cell: (row) => row.process_number ?? "—" },
    { id: "amount", header: "Valor", cell: (row) => formatBrl(row.amount) },
    { id: "due_date", header: "Vencimento", cell: (row) => formatDate(row.due_date) },
    { id: "days_overdue", header: "Dias em atraso", cell: (row) => String(row.days_overdue) },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <StatCard
          label="Total em atraso"
          value={formatBrl(summary?.total ?? 0)}
          isLoading={summaryLoading}
          negative={(summary?.total ?? 0) > 0}
        />
        <div className="rounded border border-default bg-surface p-4">
          {summary && <AgingChart data={summary.by_aging} />}
        </div>
      </div>

      <FilterBar fields={AGING_FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={overdueRows}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum lançamento em atraso."
        rowActions={(row) => (
          <div className="flex gap-2">
            <button
              type="button"
              className="text-sm text-accent underline"
              onClick={() => setHistoryFor(row)}
            >
              Histórico
            </button>
            {canSend && (
              <button
                type="button"
                className="text-sm text-accent underline"
                onClick={() => setSendingFor(row)}
              >
                Cobrar
              </button>
            )}
          </div>
        )}
      />

      {canSend && (
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-primary">Régua de cobrança automática</h2>
          <DunningRulesForm />
        </div>
      )}

      <FormModal
        open={sendingFor !== null}
        onOpenChange={(open) => {
          if (!open) setSendingFor(null);
        }}
        title="Enviar cobrança"
        description={
          sendingFor
            ? `${sendingFor.customer_name ?? "Cliente"} — ${formatBrl(sendingFor.amount)}`
            : undefined
        }
        schema={sendDunningFormSchema}
        defaultValues={DEFAULT_SEND_DUNNING_FORM_VALUES}
        serverError={sendError}
        submitLabel="Enviar"
        onSubmit={async (values) => {
          await send.mutateAsync(values);
        }}
      >
        {(form) => {
          const template = form.watch("template");
          return (
            <>
              <div className="space-y-1">
                <label htmlFor="send-channel" className="text-sm font-medium text-primary">
                  Canal
                </label>
                <select
                  id="send-channel"
                  className="h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  {...form.register("channel")}
                >
                  <option value="EMAIL">E-mail</option>
                  <option value="SMS">SMS</option>
                  <option value="WHATSAPP">WhatsApp</option>
                </select>
              </div>
              <TemplateEditor
                id="send-template"
                value={template}
                onChange={(value) => form.setValue("template", value, { shouldValidate: true })}
                error={form.formState.errors.template?.message}
              />
            </>
          );
        }}
      </FormModal>

      <DunningHistoryDrawer
        open={historyFor !== null}
        onOpenChange={(open) => {
          if (!open) setHistoryFor(null);
        }}
        transactionId={historyFor?.id ?? null}
        transactionAmount={historyFor?.amount ?? null}
      />
    </div>
  );
}

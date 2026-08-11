import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, EntityOption, FilterFieldDef } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useFilters } from "@/components/domain/useFilters";
import { listBankAccounts, listCostCenters } from "@/features/financial/api";
import {
  createTransaction,
  deleteTransaction,
  listTransactions,
  payTransaction,
  unpayTransaction,
  updateTransaction,
  type TransactionData,
  type TransactionFormPayload,
  type TransactionKind,
} from "@/features/financial/api";
import { listCustomers } from "@/features/customers/api";
import { listLawsuits } from "@/features/lawsuits/api";
import { PayTransactionDialog } from "@/features/financial/PayTransactionDialog";
import { TransactionForm } from "@/features/financial/TransactionForm";
import {
  DEFAULT_TRANSACTION_FORM_VALUES,
  transactionFormSchema,
  type TransactionFormValues,
} from "@/features/financial/schema";
import { formatBrl } from "@/lib/money";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

const KIND_LABELS: Record<TransactionKind, string> = {
  RECEITA: "Receita",
  DESPESA: "Despesa",
  TRANSFERENCIA: "Transferência",
};

const FILTER_FIELDS: FilterFieldDef[] = [
  {
    key: "kind",
    label: "Tipo",
    type: "select",
    options: Object.entries(KIND_LABELS).map(([value, label]) => ({ value, label })),
  },
  {
    key: "status",
    label: "Situação",
    type: "select",
    options: [
      { value: "open", label: "Em aberto" },
      { value: "paid", label: "Pago" },
    ],
  },
  { key: "q", label: "Descrição", type: "text" },
];

function formatDate(value: string | null): string {
  if (!value) return "—";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function toPayload(values: TransactionFormValues): TransactionFormPayload {
  const isTransfer = values.kind === "TRANSFERENCIA";
  return {
    kind: values.kind,
    debit_account_id: values.debit_account_id || null,
    credit_account_id: isTransfer ? values.credit_account_id || null : null,
    category_id: isTransfer ? null : values.category_id || null,
    cost_center_id: isTransfer ? null : values.cost_center_id || null,
    customer_id: values.customer_id || null,
    lawsuit_id: values.lawsuit_id || null,
    description: values.description || null,
    amount: values.amount,
    due_date: values.due_date,
  };
}

function toFormValues(transaction: TransactionData): TransactionFormValues {
  return {
    kind: transaction.kind,
    debit_account_id: transaction.debit_account_id ?? "",
    credit_account_id: transaction.credit_account_id ?? "",
    category_id: transaction.category_id ?? "",
    cost_center_id: transaction.cost_center_id ?? "",
    customer_id: transaction.customer_id ?? "",
    lawsuit_id: transaction.lawsuit_id ?? "",
    description: transaction.description ?? "",
    amount: String(transaction.amount),
    due_date: transaction.due_date,
  };
}

/** Regra de escrita (spec 056 §5): mesma dimensão única de contas/centros de custo
 * (financial_access=FULL, sem exigir GESTOR). */
export function TransactionsListPage(): JSX.Element {
  const { user } = useAuth();
  const canWrite = user?.financialAccess === "FULL";
  const queryClient = useQueryClient();

  const { values } = useFilters(FILTER_FIELDS);
  const kind = typeof values.kind === "string" ? (values.kind as TransactionKind) : undefined;
  const status = typeof values.status === "string" ? (values.status as "open" | "paid") : undefined;
  const q = typeof values.q === "string" ? values.q : undefined;

  const { data, isLoading, error } = useQuery({
    queryKey: ["transactions", { kind, status, q }],
    queryFn: () => listTransactions({ kind, status, q }),
  });
  const transactions = data?.items ?? [];

  const { data: accountsPage } = useQuery({
    queryKey: ["bank-accounts", "for-transaction-form"],
    queryFn: () => listBankAccounts({ status: "active" }),
  });
  const accounts = accountsPage?.items ?? [];

  const { data: costCentersPage } = useQuery({
    queryKey: ["cost-centers", "for-transaction-form"],
    queryFn: () => listCostCenters({ status: "active" }),
  });
  const costCenters = costCentersPage?.items ?? [];

  async function searchAccounts(query: string): Promise<EntityOption[]> {
    const normalized = query.trim().toLowerCase();
    return accounts
      .filter((account) => account.name.toLowerCase().includes(normalized))
      .map((account) => ({ id: account.id, label: account.name }));
  }

  async function searchCostCenters(query: string): Promise<EntityOption[]> {
    const normalized = query.trim().toLowerCase();
    return costCenters
      .filter((costCenter) => costCenter.name.toLowerCase().includes(normalized))
      .map((costCenter) => ({ id: costCenter.id, label: costCenter.name }));
  }

  async function searchCustomers(query: string): Promise<EntityOption[]> {
    const page = await listCustomers({ q: query, limit: 20 });
    return page.items.map((item) => ({ id: item.id, label: item.name }));
  }

  async function searchLawsuits(query: string): Promise<EntityOption[]> {
    const page = await listLawsuits({ q: query, limit: 20 });
    return page.items.map((item) => ({
      id: item.id,
      label: item.folder || item.process_number || item.id,
    }));
  }

  const {
    editing: editingTransaction,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
    handleConfirmDelete,
  } = useCrudResource<TransactionData, TransactionFormValues>({
    queryKey: ["transactions"],
    create: (values) => createTransaction(toPayload(values)),
    update: (transaction, values) => updateTransaction(transaction.id, toPayload(values)),
    remove: (transaction) => deleteTransaction(transaction.id),
  });

  const [payingTransaction, setPayingTransaction] = React.useState<TransactionData | null>(null);

  const unpay = useMutation({
    mutationFn: (transactionId: string) => unpayTransaction(transactionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["transactions"] }),
  });

  const pay = useMutation({
    mutationFn: ({ transactionId, paymentDate }: { transactionId: string; paymentDate: string }) =>
      payTransaction(transactionId, paymentDate),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["transactions"] }),
  });

  const columns: DataTableColumn<TransactionData>[] = [
    { id: "kind", header: "Tipo", cell: (row) => KIND_LABELS[row.kind] },
    {
      id: "description",
      header: "Descrição",
      cell: (row) =>
        row.description ??
        (row.kind === "TRANSFERENCIA"
          ? `${row.debit_account_name} → ${row.credit_account_name}`
          : (row.category_name ?? "—")),
    },
    { id: "due_date", header: "Vencimento", cell: (row) => formatDate(row.due_date) },
    {
      id: "payment_date",
      header: "Situação",
      cell: (row) => (row.payment_date ? `Pago em ${formatDate(row.payment_date)}` : "Em aberto"),
    },
    { id: "amount", header: "Valor", cell: (row) => formatBrl(row.amount) },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Financeiro — Lançamentos</h1>
        {canWrite && <Button onClick={openCreateModal}>Novo lançamento</Button>}
      </div>

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={transactions}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhum lançamento cadastrado ainda."
        rowActions={
          canWrite
            ? (row) => (
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="text-sm text-accent underline"
                    onClick={() => openEditModal(row)}
                  >
                    Editar
                  </button>
                  {row.payment_date ? (
                    <button
                      type="button"
                      className="text-sm text-accent underline"
                      onClick={() => unpay.mutate(row.id)}
                    >
                      Estornar
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="text-sm text-accent underline"
                      onClick={() => setPayingTransaction(row)}
                    >
                      Baixar
                    </button>
                  )}
                  {!row.payment_date && (
                    <button
                      type="button"
                      className="text-sm text-danger underline"
                      onClick={() => setPendingDelete(row)}
                    >
                      Excluir
                    </button>
                  )}
                </div>
              )
            : undefined
        }
      />

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingTransaction ? "Editar lançamento" : "Novo lançamento"}
        schema={transactionFormSchema}
        defaultValues={
          editingTransaction ? toFormValues(editingTransaction) : DEFAULT_TRANSACTION_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <TransactionForm
            key={editingTransaction?.id ?? "new"}
            form={form}
            onSearchAccounts={searchAccounts}
            onSearchCostCenters={searchCostCenters}
            onSearchCustomers={searchCustomers}
            onSearchLawsuits={searchLawsuits}
            currentDebitAccount={
              editingTransaction?.debit_account_id
                ? {
                    id: editingTransaction.debit_account_id,
                    label: editingTransaction.debit_account_name ?? "",
                  }
                : null
            }
            currentCreditAccount={
              editingTransaction?.credit_account_id
                ? {
                    id: editingTransaction.credit_account_id,
                    label: editingTransaction.credit_account_name ?? "",
                  }
                : null
            }
            currentCategory={
              editingTransaction?.category_id
                ? {
                    id: editingTransaction.category_id,
                    label: editingTransaction.category_name ?? "",
                  }
                : null
            }
            currentCostCenter={
              editingTransaction?.cost_center_id
                ? {
                    id: editingTransaction.cost_center_id,
                    label: editingTransaction.cost_center_name ?? "",
                  }
                : null
            }
            currentCustomer={
              editingTransaction?.customer_id
                ? {
                    id: editingTransaction.customer_id,
                    label: editingTransaction.customer_name ?? "",
                  }
                : null
            }
            currentLawsuit={
              editingTransaction?.lawsuit_id
                ? { id: editingTransaction.lawsuit_id, label: editingTransaction.lawsuit_id }
                : null
            }
          />
        )}
      </FormModal>

      <PayTransactionDialog
        open={payingTransaction !== null}
        onOpenChange={(open) => {
          if (!open) setPayingTransaction(null);
        }}
        onConfirm={async (paymentDate) => {
          if (!payingTransaction) return;
          await pay.mutateAsync({ transactionId: payingTransaction.id, paymentDate });
        }}
      />

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir lançamento?"
        description={`"${pendingDelete?.description ?? "Este lançamento"}" será excluído.`}
        confirmLabel="Excluir"
        destructive
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

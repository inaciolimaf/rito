import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { useCrudResource } from "@/components/domain/useCrudResource";
import { useFilters } from "@/components/domain/useFilters";
import { AccountBalanceCard } from "@/features/financial/AccountBalanceCard";
import { BankAccountForm } from "@/features/financial/BankAccountForm";
import {
  createBankAccount,
  deleteBankAccount,
  listBankAccounts,
  setDefaultBankAccount,
  updateBankAccount,
  type AccountKind,
  type BankAccountData,
} from "@/features/financial/api";
import {
  bankAccountFormSchema,
  DEFAULT_BANK_ACCOUNT_FORM_VALUES,
  type BankAccountFormValues,
} from "@/features/financial/schema";
import { ApiError } from "@/lib/errors";
import { useAuth } from "@/providers/AuthProvider";

const KIND_LABELS: Record<AccountKind, string> = {
  CORRENTE: "Conta corrente",
  POUPANCA: "Poupança",
  INVESTIMENTO: "Investimento",
  CARTAO_CREDITO: "Cartão de crédito",
  OUTRO: "Outro",
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
    label: "Status",
    type: "select",
    options: [
      { value: "active", label: "Ativo" },
      { value: "inactive", label: "Inativo" },
    ],
  },
];

function toPayload(values: BankAccountFormValues) {
  const isCard = values.kind === "CARTAO_CREDITO";
  return {
    kind: values.kind,
    name: values.name,
    institution_id: values.institution_id ? Number(values.institution_id) : null,
    agency: values.agency || null,
    account_number: values.account_number || null,
    cycle_day: isCard && values.cycle_day ? Number(values.cycle_day) : null,
    due_day: isCard && values.due_day ? Number(values.due_day) : null,
    initial_amount: values.initial_amount,
    is_default: values.is_default,
  };
}

/** Regra 10 (spec 055): escrita exige financial_access=FULL, sem exigir GESTOR
 * (diferente de categorias, spec 054) — mesma dimensão única de cost_centers. */
export function BankAccountsListPage(): JSX.Element {
  const { user } = useAuth();
  const canWrite = user?.financialAccess === "FULL";
  const queryClient = useQueryClient();

  const { values } = useFilters(FILTER_FIELDS);
  const kind = typeof values.kind === "string" ? (values.kind as AccountKind) : undefined;
  const status =
    typeof values.status === "string" ? (values.status as "active" | "inactive") : undefined;

  const { data, isLoading, error } = useQuery({
    queryKey: ["bank-accounts", { kind, status }],
    queryFn: () => listBankAccounts({ kind, status }),
  });
  const accounts = data?.items ?? [];
  const defaultAccount = accounts.find((account) => account.is_default);

  const {
    editing: editingAccount,
    modalOpen,
    setModalOpen,
    formError,
    pendingDelete,
    setPendingDelete,
    openCreateModal,
    openEditModal,
    handleSubmit,
    handleConfirmDelete,
  } = useCrudResource<BankAccountData, BankAccountFormValues>({
    queryKey: ["bank-accounts"],
    create: (values) => createBankAccount(toPayload(values)),
    update: (account, values) => updateBankAccount(account.id, toPayload(values)),
    remove: (account) => deleteBankAccount(account.id),
  });

  const setDefault = useMutation({
    mutationFn: (accountId: string) => setDefaultBankAccount(accountId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bank-accounts"] }),
  });

  const columns: DataTableColumn<BankAccountData>[] = [
    { id: "name", header: "Nome", cell: (row) => row.name },
    { id: "kind", header: "Tipo", cell: (row) => KIND_LABELS[row.kind] },
    { id: "institution_name", header: "Instituição", cell: (row) => row.institution_name ?? "—" },
    { id: "is_default", header: "Padrão", cell: (row) => (row.is_default ? "★ Padrão" : "") },
    { id: "is_active", header: "Status", cell: (row) => (row.is_active ? "Ativa" : "Inativa") },
  ];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-primary">Contas e cartões</h1>
        {canWrite && <Button onClick={openCreateModal}>Nova conta</Button>}
      </div>

      {defaultAccount && <AccountBalanceCard account={defaultAccount} />}

      <FilterBar fields={FILTER_FIELDS} />

      <DataTable
        columns={columns}
        data={accounts}
        getRowId={(row) => row.id}
        isLoading={isLoading}
        error={error instanceof ApiError ? error.message : null}
        emptyMessage="Nenhuma conta cadastrada ainda."
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
                  {!row.is_default && row.is_active && (
                    <button
                      type="button"
                      className="text-sm text-accent underline"
                      onClick={() => setDefault.mutate(row.id)}
                    >
                      Tornar padrão
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-sm text-danger underline"
                    onClick={() => setPendingDelete(row)}
                  >
                    Excluir
                  </button>
                </div>
              )
            : undefined
        }
      />

      <FormModal
        open={modalOpen}
        onOpenChange={setModalOpen}
        title={editingAccount ? "Editar conta" : "Nova conta"}
        schema={bankAccountFormSchema}
        defaultValues={
          editingAccount
            ? {
                kind: editingAccount.kind,
                name: editingAccount.name,
                institution_id: editingAccount.institution_id
                  ? String(editingAccount.institution_id)
                  : "",
                agency: editingAccount.agency ?? "",
                account_number: editingAccount.account_number ?? "",
                cycle_day: editingAccount.cycle_day ? String(editingAccount.cycle_day) : "",
                due_day: editingAccount.due_day ? String(editingAccount.due_day) : "",
                initial_amount: String(editingAccount.initial_amount),
                is_default: editingAccount.is_default,
              }
            : DEFAULT_BANK_ACCOUNT_FORM_VALUES
        }
        serverError={formError}
        onSubmit={handleSubmit}
      >
        {(form) => (
          <BankAccountForm form={form} institutionLabel={editingAccount?.institution_name} />
        )}
      </FormModal>

      <ConfirmDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        title="Excluir conta?"
        description={`"${pendingDelete?.name ?? ""}" será excluída.`}
        confirmLabel="Excluir"
        destructive
        onConfirm={handleConfirmDelete}
      />
    </div>
  );
}

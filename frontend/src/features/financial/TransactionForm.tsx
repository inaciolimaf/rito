import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import type { UseFormReturn } from "react-hook-form";

import { EntityPicker } from "@/components/domain/EntityPicker";
import { MoneyField } from "@/components/domain/MoneyField";
import type { EntityOption } from "@/components/domain/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AttachmentList } from "@/features/attachments/AttachmentList";
import { FileDropzone } from "@/features/attachments/FileDropzone";
import { CategorySelect } from "@/features/financial/CategorySelect";
import { FinancialRecurrenceFields } from "@/features/financial/FinancialRecurrenceFields";
import { InstallmentFields } from "@/features/financial/InstallmentFields";
import { InternalToggle } from "@/features/financial/InternalToggle";
import {
  listTransactionAttachments,
  uploadTransactionAttachment,
  type EntryType,
  type TransactionKind,
} from "@/features/financial/api";
import type { TransactionFormValues } from "@/features/financial/schema";

export interface TransactionFormProps {
  form: UseFormReturn<TransactionFormValues>;
  /** Parcelamento/recorrência só fazem sentido na criação (regras 1/4, spec 057) — o
   * backend nem aceita esses campos em `TransactionUpdateRequest`. Anexos (spec 058)
   * só fazem sentido em edição — precisam de um `transactionId` que só existe depois
   * de criado. */
  mode: "create" | "edit";
  transactionId?: string;
  onSearchAccounts: (query: string) => Promise<EntityOption[]>;
  onSearchCostCenters: (query: string) => Promise<EntityOption[]>;
  onSearchCustomers: (query: string) => Promise<EntityOption[]>;
  onSearchLawsuits: (query: string) => Promise<EntityOption[]>;
  currentDebitAccount?: EntityOption | null;
  currentCreditAccount?: EntityOption | null;
  currentCategory?: EntityOption | null;
  currentCostCenter?: EntityOption | null;
  currentCustomer?: EntityOption | null;
  currentLawsuit?: EntityOption | null;
}

const SERIES_MODE_LABELS: Record<TransactionFormValues["seriesMode"], string> = {
  none: "Lançamento único",
  installment: "Parcelado",
  recurrence: "Recorrente",
};

const KIND_LABELS: Record<TransactionKind, string> = {
  RECEITA: "Receita",
  DESPESA: "Despesa",
  TRANSFERENCIA: "Transferência",
};

const SELECT_CLASS =
  "h-10 w-full rounded border border-default bg-surface px-3 text-sm text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent";

/** Campos condicionais pelos 3 tipos (regra 2, spec 056): transferência troca a conta de
 * destino no lugar de categoria/centro de custo, que ela não usa.
 *
 * Cada `EntityPicker` guarda o par (id, nome) escolhido em estado local — o form em si só
 * guarda o id (é o que a API espera). Reconstruir o nome a partir do id a cada render (via
 * `currentX?.id === valorAtual ? currentX.label : ...`) só cobre o registro que já veio
 * carregado da API; uma escolha nova feita durante a sessão (busca → clique) não tinha
 * label nenhum pra reconstruir e o chip mostrava o UUID cru. O componente é remontado
 * (via `key` no chamador) toda vez que troca entre criar/editar, então o estado local
 * nunca vaza de um registro pro outro. */
export function TransactionForm({
  form,
  mode,
  transactionId,
  onSearchAccounts,
  onSearchCostCenters,
  onSearchCustomers,
  onSearchLawsuits,
  currentDebitAccount = null,
  currentCreditAccount = null,
  currentCategory = null,
  currentCostCenter = null,
  currentCustomer = null,
  currentLawsuit = null,
}: TransactionFormProps): JSX.Element {
  const {
    register,
    watch,
    setValue,
    control,
    formState: { errors },
  } = form;

  const kind = watch("kind");
  const isTransfer = kind === "TRANSFERENCIA";
  const seriesMode = watch("seriesMode");

  const queryClient = useQueryClient();
  const { data: attachments } = useQuery({
    queryKey: ["transaction-attachments", transactionId],
    queryFn: () => listTransactionAttachments(transactionId!),
    enabled: mode === "edit" && !!transactionId,
  });

  async function invalidateAttachments(): Promise<void> {
    await queryClient.invalidateQueries({ queryKey: ["transaction-attachments", transactionId] });
  }

  const [debitAccount, setDebitAccount] = React.useState<EntityOption | null>(currentDebitAccount);
  const [creditAccount, setCreditAccount] = React.useState<EntityOption | null>(
    currentCreditAccount,
  );
  const [category, setCategory] = React.useState<EntityOption | null>(currentCategory);
  const [costCenter, setCostCenter] = React.useState<EntityOption | null>(currentCostCenter);
  const [customer, setCustomer] = React.useState<EntityOption | null>(currentCustomer);
  const [lawsuit, setLawsuit] = React.useState<EntityOption | null>(currentLawsuit);

  return (
    <>
      <div className="space-y-1">
        <Label htmlFor="transaction-kind">Tipo</Label>
        <select
          id="transaction-kind"
          className={SELECT_CLASS}
          {...register("kind")}
          onChange={(event) => {
            setValue("kind", event.target.value as TransactionKind, { shouldDirty: true });
            setValue("category_id", "", { shouldDirty: true });
            setValue("cost_center_id", "", { shouldDirty: true });
            setValue("credit_account_id", "", { shouldDirty: true });
            setCategory(null);
            setCostCenter(null);
            setCreditAccount(null);
          }}
        >
          {Object.entries(KIND_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1">
        <Label htmlFor="transaction-debit-account">
          {isTransfer ? "Conta de origem" : "Conta"}
        </Label>
        <EntityPicker
          value={debitAccount ? [debitAccount] : []}
          onChange={(next) => {
            const option = next[0] ?? null;
            setDebitAccount(option);
            setValue("debit_account_id", option?.id ?? "", { shouldDirty: true });
          }}
          onSearch={onSearchAccounts}
          label={isTransfer ? "Conta de origem" : "Conta"}
          placeholder="Buscar conta…"
        />
        {errors.debit_account_id && (
          <p className="text-sm text-danger">{errors.debit_account_id.message}</p>
        )}
      </div>

      {isTransfer && (
        <div className="space-y-1">
          <Label htmlFor="transaction-credit-account">Conta de destino</Label>
          <EntityPicker
            value={creditAccount ? [creditAccount] : []}
            onChange={(next) => {
              const option = next[0] ?? null;
              setCreditAccount(option);
              setValue("credit_account_id", option?.id ?? "", { shouldDirty: true });
            }}
            onSearch={onSearchAccounts}
            label="Conta de destino"
            placeholder="Buscar conta…"
          />
          {errors.credit_account_id && (
            <p className="text-sm text-danger">{errors.credit_account_id.message}</p>
          )}
        </div>
      )}

      {!isTransfer && (
        <>
          <CategorySelect
            type={kind as EntryType}
            value={category}
            onChange={(option) => {
              setCategory(option);
              setValue("category_id", option?.id ?? "", { shouldDirty: true });
            }}
          />
          {errors.category_id && (
            <p className="text-sm text-danger">{errors.category_id.message}</p>
          )}

          <div className="space-y-1">
            <Label htmlFor="transaction-cost-center">Centro de custo</Label>
            <EntityPicker
              value={costCenter ? [costCenter] : []}
              onChange={(next) => {
                const option = next[0] ?? null;
                setCostCenter(option);
                setValue("cost_center_id", option?.id ?? "", { shouldDirty: true });
              }}
              onSearch={onSearchCostCenters}
              label="Centro de custo"
              placeholder="Buscar centro de custo…"
            />
          </div>
        </>
      )}

      <div className="space-y-1">
        <Label htmlFor="transaction-customer">Cliente (opcional)</Label>
        <EntityPicker
          value={customer ? [customer] : []}
          onChange={(next) => {
            const option = next[0] ?? null;
            setCustomer(option);
            setValue("customer_id", option?.id ?? "", { shouldDirty: true });
            if (!option) {
              setLawsuit(null);
              setValue("lawsuit_id", "", { shouldDirty: true });
            }
          }}
          onSearch={onSearchCustomers}
          label="Cliente"
          placeholder="Buscar cliente…"
        />
      </div>

      {customer && (
        <div className="space-y-1">
          <Label htmlFor="transaction-lawsuit">Processo (opcional)</Label>
          <EntityPicker
            value={lawsuit ? [lawsuit] : []}
            onChange={(next) => {
              const option = next[0] ?? null;
              setLawsuit(option);
              setValue("lawsuit_id", option?.id ?? "", { shouldDirty: true });
            }}
            onSearch={onSearchLawsuits}
            label="Processo"
            placeholder="Buscar processo…"
          />
          {errors.lawsuit_id && <p className="text-sm text-danger">{errors.lawsuit_id.message}</p>}
        </div>
      )}

      <div className="space-y-1">
        <Label htmlFor="transaction-description">Descrição</Label>
        <Input id="transaction-description" {...register("description")} />
      </div>

      <MoneyField control={control} name="amount" label="Valor" />
      {errors.amount && <p className="text-sm text-danger">{errors.amount.message}</p>}

      <div className="space-y-1">
        <Label htmlFor="transaction-due-date">Vencimento</Label>
        <Input id="transaction-due-date" type="date" {...register("due_date")} />
        {errors.due_date && <p className="text-sm text-danger">{errors.due_date.message}</p>}
      </div>

      {mode === "create" && (
        <div className="space-y-2 border-t border-default pt-3">
          <Label htmlFor="transaction-series-mode">Modo</Label>
          <select id="transaction-series-mode" className={SELECT_CLASS} {...register("seriesMode")}>
            {Object.entries(SERIES_MODE_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>

          {seriesMode === "installment" && <InstallmentFields form={form} />}
          {seriesMode === "recurrence" && <FinancialRecurrenceFields form={form} />}
        </div>
      )}

      <InternalToggle form={form} />

      {mode === "edit" && transactionId && (
        <div className="space-y-2 border-t border-default pt-3">
          <Label>Anexos</Label>
          <AttachmentList
            attachments={attachments ?? []}
            onRemoved={() => void invalidateAttachments()}
          />
          <FileDropzone
            onFiles={(files) => {
              void Promise.all(
                files.map((file) => uploadTransactionAttachment(transactionId, file)),
              ).then(invalidateAttachments);
            }}
          />
        </div>
      )}
    </>
  );
}

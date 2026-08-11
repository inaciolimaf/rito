import { z } from "zod";

export const financialCategoryFormSchema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
  type: z.enum(["RECEITA", "DESPESA"]),
  dre_group_id: z.string().min(1, "Grupo DRE é obrigatório."),
});

export type FinancialCategoryFormValues = z.infer<typeof financialCategoryFormSchema>;

export const DEFAULT_FINANCIAL_CATEGORY_FORM_VALUES: FinancialCategoryFormValues = {
  name: "",
  type: "DESPESA",
  dre_group_id: "",
};

export const costCenterFormSchema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
});

export type CostCenterFormValues = z.infer<typeof costCenterFormSchema>;

export const DEFAULT_COST_CENTER_FORM_VALUES: CostCenterFormValues = { name: "" };

const ACCOUNT_KINDS = ["CORRENTE", "POUPANCA", "INVESTIMENTO", "CARTAO_CREDITO", "OUTRO"] as const;

export const bankAccountFormSchema = z
  .object({
    kind: z.enum(ACCOUNT_KINDS),
    name: z.string().min(1, "Nome é obrigatório."),
    institution_id: z.string(),
    agency: z.string(),
    account_number: z.string(),
    cycle_day: z.string(),
    due_day: z.string(),
    initial_amount: z.string(),
    is_default: z.boolean(),
  })
  .refine(
    (values) =>
      values.kind !== "CARTAO_CREDITO" ||
      (values.cycle_day.trim() !== "" && values.due_day.trim() !== ""),
    { message: "Cartão de crédito exige fechamento e vencimento.", path: ["cycle_day"] },
  );

export type BankAccountFormValues = z.infer<typeof bankAccountFormSchema>;

export const DEFAULT_BANK_ACCOUNT_FORM_VALUES: BankAccountFormValues = {
  kind: "CORRENTE",
  name: "",
  institution_id: "",
  agency: "",
  account_number: "",
  cycle_day: "",
  due_day: "",
  initial_amount: "0",
  is_default: false,
};

const TRANSACTION_KINDS = ["RECEITA", "DESPESA", "TRANSFERENCIA"] as const;
const FINANCIAL_RECURRENCES = ["MENSAL", "BIMESTRAL", "TRIMESTRAL", "SEMESTRAL", "ANUAL"] as const;
const SERIES_MODES = ["none", "installment", "recurrence"] as const;

/** Espelha as regras 1/2/3 (spec 056) e 1/11 (spec 057, parcelamento × recorrência são
 * exclusivos) no cliente, pra dar 422 sem round-trip — o backend continua sendo a fonte
 * de verdade (`_TransactionMixin._validate_shape`/`TransactionCreateRequest._validate_series`). */
export const transactionFormSchema = z
  .object({
    kind: z.enum(TRANSACTION_KINDS),
    debit_account_id: z.string(),
    credit_account_id: z.string(),
    category_id: z.string(),
    cost_center_id: z.string(),
    customer_id: z.string(),
    lawsuit_id: z.string(),
    description: z.string(),
    amount: z.string().min(1, "Valor é obrigatório."),
    due_date: z.string().min(1, "Vencimento é obrigatório."),
    seriesMode: z.enum(SERIES_MODES),
    installmentCount: z.string(),
    recurrencePeriod: z.enum(FINANCIAL_RECURRENCES),
    recurrenceUntilDate: z.string(),
  })
  .refine((values) => values.debit_account_id.trim() !== "", {
    message: "Conta é obrigatória.",
    path: ["debit_account_id"],
  })
  .refine(
    (values) =>
      values.kind !== "TRANSFERENCIA" ||
      (values.credit_account_id.trim() !== "" &&
        values.credit_account_id !== values.debit_account_id),
    {
      message: "Transferência exige uma conta de destino diferente da origem.",
      path: ["credit_account_id"],
    },
  )
  .refine(
    (values) =>
      values.kind === "TRANSFERENCIA" ||
      (values.category_id.trim() !== "" && values.cost_center_id.trim() !== ""),
    { message: "Categoria e centro de custo são obrigatórios.", path: ["category_id"] },
  )
  .refine((values) => values.lawsuit_id.trim() === "" || values.customer_id.trim() !== "", {
    message: "Vincular processo exige cliente.",
    path: ["lawsuit_id"],
  })
  .refine(
    (values) => {
      if (values.seriesMode !== "installment") return true;
      const count = Number(values.installmentCount);
      return Number.isInteger(count) && count >= 2 && count <= 100;
    },
    { message: "Parcelamento vai de 2 a 100 vezes.", path: ["installmentCount"] },
  );

export type TransactionFormValues = z.infer<typeof transactionFormSchema>;

export const DEFAULT_TRANSACTION_FORM_VALUES: TransactionFormValues = {
  kind: "RECEITA",
  debit_account_id: "",
  credit_account_id: "",
  category_id: "",
  cost_center_id: "",
  customer_id: "",
  lawsuit_id: "",
  description: "",
  amount: "",
  due_date: "",
  seriesMode: "none",
  installmentCount: "",
  recurrencePeriod: "MENSAL",
  recurrenceUntilDate: "",
};

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

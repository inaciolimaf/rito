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

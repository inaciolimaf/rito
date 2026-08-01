import { z } from "zod";

export const customerOriginFormSchema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
});

export type CustomerOriginFormValues = z.infer<typeof customerOriginFormSchema>;

export const DEFAULT_CUSTOMER_ORIGIN_FORM_VALUES: CustomerOriginFormValues = {
  name: "",
};

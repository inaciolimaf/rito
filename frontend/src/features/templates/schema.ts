import { z } from "zod";

export const templateFormSchema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
  type: z.enum(["CONTRATO", "PETICAO", "RECURSO", "DOCUMENTO"]),
});

export type TemplateFormValues = z.infer<typeof templateFormSchema>;

export const DEFAULT_TEMPLATE_FORM_VALUES: TemplateFormValues = {
  name: "",
  type: "CONTRATO",
};

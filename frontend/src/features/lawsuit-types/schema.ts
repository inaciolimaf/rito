import { z } from "zod";

export const lawsuitTypeFormSchema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
  action_group_id: z.string().min(1, "Grupo de ação é obrigatório."),
});

export type LawsuitTypeFormValues = z.infer<typeof lawsuitTypeFormSchema>;

export const DEFAULT_LAWSUIT_TYPE_FORM_VALUES: LawsuitTypeFormValues = {
  name: "",
  action_group_id: "",
};

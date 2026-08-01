import { z } from "zod";

export const actionGroupFormSchema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
  publications_user_id: z.string().nullable(),
});

export type ActionGroupFormValues = z.infer<typeof actionGroupFormSchema>;

export const DEFAULT_ACTION_GROUP_FORM_VALUES: ActionGroupFormValues = {
  name: "",
  publications_user_id: null,
};

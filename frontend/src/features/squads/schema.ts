import { z } from "zod";

export const squadFormSchema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
  member_ids: z.array(z.string()),
});

export type SquadFormValues = z.infer<typeof squadFormSchema>;

export const DEFAULT_SQUAD_FORM_VALUES: SquadFormValues = {
  name: "",
  member_ids: [],
};

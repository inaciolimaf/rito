import { z } from "zod";

export const stageFormSchema = z
  .object({
    name: z.string().min(1, "Nome é obrigatório."),
    step_id: z.string().min(1, "Fase é obrigatória."),
    enable_stagnant_days: z.boolean(),
    stagnant_days: z.string(),
  })
  .refine(
    (values) =>
      !values.enable_stagnant_days ||
      (values.stagnant_days.trim() !== "" && Number(values.stagnant_days) > 0),
    {
      message: "Informe um número de dias maior que zero.",
      path: ["stagnant_days"],
    },
  );

export type StageFormValues = z.infer<typeof stageFormSchema>;

export const DEFAULT_STAGE_FORM_VALUES: StageFormValues = {
  name: "",
  step_id: "",
  enable_stagnant_days: false,
  stagnant_days: "",
};

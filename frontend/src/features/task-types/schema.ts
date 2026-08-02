import { z } from "zod";

export const taskTypeFormSchema = z.object({
  name: z.string().min(1, "Informe o nome da tarefa.").max(200),
  step_id: z.string(),
  complexity: z.string(),
  duration: z.string(),
  reward: z
    .string()
    .refine(
      (value) => value === "" || (Number.isInteger(Number(value)) && Number(value) >= 0),
      "Pontuação inteira, zero ou mais.",
    ),
  show_in_schedule: z.boolean(),
});

export type TaskTypeFormValues = z.infer<typeof taskTypeFormSchema>;

export const DEFAULT_TASK_TYPE_FORM_VALUES: TaskTypeFormValues = {
  name: "",
  step_id: "",
  complexity: "",
  duration: "",
  reward: "",
  show_in_schedule: false,
};

export const COMPLEXITY_OPTIONS = [
  { value: "SIMPLES", label: "Simples" },
  { value: "MEDIA", label: "Média" },
  { value: "MEDIA_ALTA", label: "Média alta" },
  { value: "ALTA", label: "Alta" },
  { value: "ALTISSIMA", label: "Altíssima" },
];

export const DURATION_OPTIONS = [
  { value: "MIN_8", label: "8 min" },
  { value: "MIN_15", label: "15 min" },
  { value: "MIN_30", label: "30 min" },
  { value: "HOUR_1", label: "1 hora" },
  { value: "HOUR_2_PLUS", label: "+2 horas" },
];

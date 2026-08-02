import { z } from "zod";

/** Formulário da nova tarefa (spec 032 §6). Obrigatórios: processo, tipo e ao menos
 * um responsável OU um time (regra 1 — o servidor valida o pós-expansão). */
export const taskFormSchema = z
  .object({
    lawsuit_id: z.string().min(1, "Selecione o processo."),
    task_type_id: z.string().min(1, "Selecione a tarefa."),
    assignee_mode: z.enum(["users", "squad"]),
    user_ids: z.array(z.object({ id: z.string(), label: z.string() })),
    squad_id: z.string(),
    scheduled_date: z.string(),
    scheduled_time: z.string(),
    end_date: z.string(),
    end_time: z.string(),
    deadline_date: z.string(),
    all_day: z.boolean(),
    location: z.string(),
    comments: z.string(),
  })
  .superRefine((values, context) => {
    if (values.assignee_mode === "users" && values.user_ids.length === 0) {
      context.addIssue({
        code: "custom",
        path: ["user_ids"],
        message: "Adicione pelo menos 1 responsável.",
      });
    }
    if (values.assignee_mode === "squad" && !values.squad_id) {
      context.addIssue({
        code: "custom",
        path: ["squad_id"],
        message: "Selecione o time.",
      });
    }
    if (values.end_time && !values.end_date) {
      context.addIssue({
        code: "custom",
        path: ["end_date"],
        message: "Hora de término exige data de término.",
      });
    }
    if (values.end_date && values.scheduled_date && values.end_date < values.scheduled_date) {
      context.addIssue({
        code: "custom",
        path: ["end_date"],
        message: "Término não pode ser anterior ao compromisso.",
      });
    }
  });

export type TaskFormValues = z.infer<typeof taskFormSchema>;

export const DEFAULT_TASK_FORM_VALUES: TaskFormValues = {
  lawsuit_id: "",
  task_type_id: "",
  assignee_mode: "users",
  user_ids: [],
  squad_id: "",
  scheduled_date: "",
  scheduled_time: "",
  end_date: "",
  end_time: "",
  deadline_date: "",
  all_day: false,
  location: "",
  comments: "",
};

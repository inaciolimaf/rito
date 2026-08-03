import { z } from "zod";

const RECURRENCE_PERIODS = [
  "DIARIA",
  "SEMANAL",
  "QUINZENAL",
  "MENSAL",
  "BIMESTRAL",
  "TRIMESTRAL",
  "SEMESTRAL",
  "ANUAL",
] as const;

const RECURRENCE_WEEKS = ["DIA_EXATO", "PRIMEIRA", "SEGUNDA", "TERCEIRA", "ULTIMA"] as const;

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
    is_important: z.boolean(),
    is_urgent: z.boolean(),
    is_future: z.boolean(),
    is_private: z.boolean(),
    show_in_schedule: z.boolean(),
    // Recorrência (spec 034 §6): checkbox libera periodicidade + modo + limite.
    is_recurring: z.boolean(),
    recurrence_period: z.enum(RECURRENCE_PERIODS),
    recurrence_repeat_on: z.enum(RECURRENCE_WEEKS),
    recurrence_limit_mode: z.enum(["none", "until", "max"]),
    recurrence_until_date: z.string(),
    recurrence_max_occurrences: z.string(),
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
    if (values.is_recurring) {
      // A série ancora na data do compromisso — sem ela não há próxima ocorrência.
      if (!values.scheduled_date) {
        context.addIssue({
          code: "custom",
          path: ["scheduled_date"],
          message: "Tarefa recorrente exige data.",
        });
      }
      if (values.recurrence_limit_mode === "until" && !values.recurrence_until_date) {
        context.addIssue({
          code: "custom",
          path: ["recurrence_until_date"],
          message: "Informe a data limite da série.",
        });
      }
      if (values.recurrence_limit_mode === "max") {
        const max = Number(values.recurrence_max_occurrences);
        if (!Number.isInteger(max) || max < 1) {
          context.addIssue({
            code: "custom",
            path: ["recurrence_max_occurrences"],
            message: "Informe ao menos 1 ocorrência.",
          });
        }
      }
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
  is_important: false,
  is_urgent: false,
  is_future: false,
  is_private: false,
  show_in_schedule: false,
  is_recurring: false,
  recurrence_period: "SEMANAL",
  recurrence_repeat_on: "DIA_EXATO",
  recurrence_limit_mode: "none",
  recurrence_until_date: "",
  recurrence_max_occurrences: "",
};

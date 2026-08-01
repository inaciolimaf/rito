import { z } from "zod";

const _OAB_PATTERN = /^\d{4,6}\/[A-Z]{2}$/;

// Time inputs nativos (`<input type="time">`) devolvem "HH:MM" — o backend espera
// "HH:MM:SS" (work_start/work_end) e duração ISO 8601 "PTxHyM" (work_interval, spec
// 012). As conversões ficam em WorkScheduleField/UserForm, não aqui.
export const userFormSchema = z.object({
  name: z.string().min(1, "Nome é obrigatório."),
  role: z.enum(["GESTOR", "ADMINISTRADOR", "COLABORADOR"]),
  financial_access: z.enum(["NONE", "READ_ONLY", "FULL"]),
  occupation_id: z.string().optional(),
  identification: z.string().optional(),
  document: z.string().optional(),
  birthdate: z.string().optional(),
  number_ctps: z.string().optional(),
  number_oab: z
    .string()
    .optional()
    .refine((value) => !value || _OAB_PATTERN.test(value), "OAB deve estar no formato NNNNNN/UF."),
  cellphone: z.string().optional(),
  phone: z.string().optional(),
  salary: z.string().optional(),
  admission_date: z.string().optional(),
  resignation_date: z.string().optional(),
  workStart: z.string().optional(),
  workInterval: z.string().optional(),
  workEnd: z.string().optional(),
  points_goal: z.string().optional(),
  report_deadline: z.boolean(),
  report_deleted: z.boolean(),
  is_responsible: z.boolean(),
});

export type UserFormValues = z.infer<typeof userFormSchema>;

export const DEFAULT_USER_FORM_VALUES: UserFormValues = {
  name: "",
  role: "COLABORADOR",
  financial_access: "NONE",
  occupation_id: "",
  identification: "",
  document: "",
  birthdate: "",
  number_ctps: "",
  number_oab: "",
  cellphone: "",
  phone: "",
  salary: "",
  admission_date: "",
  resignation_date: "",
  workStart: "",
  workInterval: "",
  workEnd: "",
  points_goal: "",
  report_deadline: false,
  report_deleted: false,
  is_responsible: false,
};

export const inviteUserSchema = z.object({
  email: z.string().email("E-mail inválido."),
  role: z.enum(["GESTOR", "ADMINISTRADOR", "COLABORADOR"]),
  financial_access: z.enum(["NONE", "READ_ONLY", "FULL"]),
  occupation_id: z.string().optional(),
});

export type InviteUserFormValues = z.infer<typeof inviteUserSchema>;

export const DEFAULT_INVITE_VALUES: InviteUserFormValues = {
  email: "",
  role: "COLABORADOR",
  financial_access: "NONE",
  occupation_id: "",
};

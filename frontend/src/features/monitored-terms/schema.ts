import { z } from "zod";

export const monitoredTermFormSchema = z
  .object({
    kind: z.enum(["OAB", "CPF", "CNPJ"]),
    value: z.string().min(1, "Número do termo é obrigatório."),
    oab_state: z.string(),
    label: z.string(),
    user_id: z.string(),
    backfill_from: z.string(),
  })
  .superRefine((values, ctx) => {
    const digits = values.value.replace(/\D/g, "");
    if (values.kind === "OAB") {
      if (values.value.trim() !== digits) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["value"],
          message: "Número de OAB deve conter apenas dígitos.",
        });
      }
      if (!values.oab_state) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["oab_state"],
          message: "UF da OAB é obrigatória.",
        });
      }
    }
    if (values.kind === "CPF" && digits.length !== 11) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["value"],
        message: "CPF deve ter 11 dígitos.",
      });
    }
    if (values.kind === "CNPJ" && digits.length !== 14) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["value"],
        message: "CNPJ deve ter 14 dígitos.",
      });
    }
  });

export type MonitoredTermFormValues = z.infer<typeof monitoredTermFormSchema>;

export const DEFAULT_MONITORED_TERM_FORM_VALUES: MonitoredTermFormValues = {
  kind: "OAB",
  value: "",
  oab_state: "",
  label: "",
  user_id: "",
  backfill_from: "",
};

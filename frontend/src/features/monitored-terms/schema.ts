import { z } from "zod";

import { isValidCnpj, isValidCpf } from "@/lib/br-documents";

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
    // Spec 138, regra 7: o backend valida o dígito verificador
    // (`monitored_terms/schemas.py` → `core/br_documents.py`). Checar só o comprimento
    // aqui é pior que não checar nada: a tela diz "11 dígitos", o usuário digita 11
    // dígitos, e o servidor responde "CPF inválido." contradizendo o que a tela acabou
    // de afirmar. `lib/br-documents.ts` é o mesmo algoritmo, espelhado.
    if (values.kind === "CPF" && !isValidCpf(digits)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["value"],
        message:
          digits.length !== 11 ? "CPF deve ter 11 dígitos." : "CPF inválido — confira os números.",
      });
    }
    if (values.kind === "CNPJ" && !isValidCnpj(digits)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["value"],
        message:
          digits.length !== 14
            ? "CNPJ deve ter 14 dígitos."
            : "CNPJ inválido — confira os números.",
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

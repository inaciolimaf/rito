import { z } from "zod";

import { PARTY_POLES } from "@/features/lawsuits/PartySelector";

export const lawsuitFormSchema = z
  .object({
    user_id: z.string().min(1, "Responsável é obrigatório."),
    lawsuit_type_id: z.string().min(1, "Tipo de ação é obrigatório."),
    stage_id: z.string().min(1, "Etapa é obrigatória."),
    // Regra 1 (spec 023): no mínimo 1 parte.
    parties: z
      .array(
        z.object({
          customer_id: z.string().min(1),
          label: z.string(),
          pole: z.enum(PARTY_POLES),
          is_client: z.boolean(),
        }),
      )
      .min(1, "Adicione pelo menos uma parte."),
    court_id: z.string().optional(),
    court_system_id: z.string().optional(),
    process_number: z.string().optional(),
    protocol_number: z.string().optional(),
    originating_process: z.string().optional(),
    folder: z.string().max(30, "Máximo de 30 caracteres.").optional(),
    filing_year: z.string().optional(),
    judiciary: z.string().optional(),
    county: z.string().optional(),
    court_division: z.string().optional(),
    process_date: z.string().optional(),
    notes: z.string().optional(),
    // Honorários e ciclo (spec 024) — valores crus com ponto ("1234.56"), máscara é só tela.
    case_value: z.string().optional(),
    fees_value: z.string().optional(),
    fees_percentage: z.string().optional(),
    contingency: z.union([z.enum(["PROVAVEL", "POSSIVEL", "REMOTA"]), z.literal("")]).optional(),
    closure_date: z.string().optional(),
    transit_date: z.string().optional(),
    archived_date: z.string().optional(),
    outcome: z.union([z.enum(["GANHO", "PERDIDO", "ACORDO"]), z.literal("")]).optional(),
  })
  // Regra 3: fechamento ≤ trânsito ≤ arquivamento.
  .refine(
    (values) =>
      !values.closure_date || !values.transit_date || values.transit_date >= values.closure_date,
    {
      message: "Trânsito em julgado não pode ser anterior ao fechamento.",
      path: ["transit_date"],
    },
  )
  .refine(
    (values) =>
      !values.transit_date || !values.archived_date || values.archived_date >= values.transit_date,
    {
      message: "Arquivamento não pode ser anterior ao trânsito em julgado.",
      path: ["archived_date"],
    },
  )
  // Regra 4: resultado exige processo fechado.
  .refine((values) => !values.outcome || values.closure_date, {
    message: "Resultado só é aceito com a data de fechamento preenchida.",
    path: ["outcome"],
  });

export type LawsuitFormValues = z.infer<typeof lawsuitFormSchema>;

export const DEFAULT_LAWSUIT_FORM_VALUES: LawsuitFormValues = {
  user_id: "",
  lawsuit_type_id: "",
  stage_id: "",
  parties: [],
  court_id: "",
  court_system_id: "",
  process_number: "",
  protocol_number: "",
  originating_process: "",
  folder: "",
  filing_year: "",
  judiciary: "",
  county: "",
  court_division: "",
  process_date: "",
  notes: "",
  case_value: "",
  fees_value: "",
  fees_percentage: "",
  contingency: "",
  closure_date: "",
  transit_date: "",
  archived_date: "",
  outcome: "",
};

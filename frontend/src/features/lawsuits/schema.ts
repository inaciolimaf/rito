import { z } from "zod";

export const lawsuitFormSchema = z.object({
  user_id: z.string().min(1, "Responsável é obrigatório."),
  lawsuit_type_id: z.string().min(1, "Tipo de ação é obrigatório."),
  stage_id: z.string().min(1, "Etapa é obrigatória."),
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
});

export type LawsuitFormValues = z.infer<typeof lawsuitFormSchema>;

export const DEFAULT_LAWSUIT_FORM_VALUES: LawsuitFormValues = {
  user_id: "",
  lawsuit_type_id: "",
  stage_id: "",
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
};

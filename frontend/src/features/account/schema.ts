import { z } from "zod";

// As mesmas 8 timezones de app/domain/account/schemas.py (spec 011, seção 4) — sem um
// pacote compartilhado entre backend/frontend, a lista vive duplicada nos dois lugares;
// mudar uma exige mudar a outra.
export const ALLOWED_TIMEZONES = [
  { value: "America/Sao_Paulo", label: "Brasília" },
  { value: "America/Noronha", label: "Fernando de Noronha" },
  { value: "America/Belem", label: "Belém" },
  { value: "America/Manaus", label: "Manaus" },
  { value: "America/Rio_Branco", label: "Rio Branco" },
  { value: "Europe/Lisbon", label: "Portugal Continental" },
  { value: "Atlantic/Madeira", label: "Madeira" },
  { value: "Atlantic/Azores", label: "Açores" },
] as const;

const _CEP_PATTERN = /^\d{5}-\d{3}$/;

// O algoritmo completo de dígito verificador de CPF/CNPJ mora só no backend
// (app/core/br_documents.py) — o mesmo precedente da política de senha (spec 009,
// Descobertas): o cliente confere só o formato, o 422 do servidor é quem valida de fato.
function isCpfOrCnpjLength(value: string): boolean {
  const digits = value.replace(/\D/g, "");
  return digits.length === 11 || digits.length === 14;
}

export const accountSchema = z.object({
  name: z.string().min(1, "Razão social é obrigatória."),
  alternate_name: z.string().min(1, "Nome fantasia é obrigatório."),
  identification: z.string().refine(isCpfOrCnpjLength, "CPF ou CNPJ com tamanho inválido."),
  country: z.string().min(1, "País é obrigatório."),
  state: z.string().length(2, "UF deve ter 2 letras."),
  city: z.string().min(1, "Cidade é obrigatória."),
  postal_code: z.string().regex(_CEP_PATTERN, "CEP deve estar no formato 99999-999."),
  street: z.string().min(1, "Endereço é obrigatório."),
  region: z.string().min(1, "Bairro é obrigatório."),
  cellphone: z.string().min(1, "Celular é obrigatório."),
  phone: z.string().min(1, "Telefone é obrigatório."),
  email: z.string().email("E-mail principal inválido."),
  email_admin: z.string().email("E-mail financeiro inválido."),
  site: z.string(),
  timezone: z.enum(ALLOWED_TIMEZONES.map((tz) => tz.value) as [string, ...string[]], {
    errorMap: () => ({ message: "Selecione um timezone válido." }),
  }),
});

export type AccountFormValues = z.infer<typeof accountSchema>;

export const DEFAULT_ACCOUNT_VALUES: AccountFormValues = {
  name: "",
  alternate_name: "",
  identification: "",
  country: "BRASIL",
  state: "",
  city: "",
  postal_code: "",
  street: "",
  region: "",
  cellphone: "",
  phone: "",
  email: "",
  email_admin: "",
  site: "",
  timezone: "America/Sao_Paulo",
};

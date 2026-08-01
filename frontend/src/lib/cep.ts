// ViaCEP é chamado direto do browser (sem proxy no backend) — é só autofill de UX,
// não tem dado sensível nem precisa de auditoria; CORS da ViaCEP já permite chamada
// client-side (spec 011, regra 2).
const VIACEP_BASE_URL = "https://viacep.com.br/ws";

export interface CepResult {
  state: string;
  city: string;
  street: string;
  region: string;
}

interface ViaCepResponseBody {
  erro?: boolean;
  uf?: string;
  localidade?: string;
  logradouro?: string;
  bairro?: string;
}

/** Devolve null se o CEP não existir ou a busca falhar — o formulário segue preenchível
 * manualmente, isso nunca bloqueia o usuário. */
export async function lookupCep(cep: string): Promise<CepResult | null> {
  const digits = cep.replace(/\D/g, "");
  if (digits.length !== 8) return null;

  try {
    const response = await fetch(`${VIACEP_BASE_URL}/${digits}/json/`);
    if (!response.ok) return null;

    const body = (await response.json()) as ViaCepResponseBody;
    if (body.erro || !body.uf || !body.localidade) return null;

    return {
      state: body.uf,
      city: body.localidade,
      street: body.logradouro ?? "",
      region: body.bairro ?? "",
    };
  } catch {
    return null;
  }
}

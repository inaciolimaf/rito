import type { ApiError } from "@/lib/errors";

export interface ServerFieldError {
  field: string;
  message: string;
}

/** O 422 do servidor separado em duas pilhas: o que tem campo e o que não tem.
 *
 * Spec 138, regra 5. O mapeamento antigo só olhava `loc[loc.length - 1]` e assumia que
 * ali sempre havia um campo do formulário. Não há, em três formatos que o backend usa de
 * verdade:
 *
 * - `errors` como **lista de strings** — é assim que a política de senha manda os
 *   critérios (`users/router.py`, `auth/router.py`);
 * - erro de `model_validator` do Pydantic, que chega com `loc: ["body"]` (a regra vale
 *   para o objeto inteiro, não para um campo) — jornada e demissão em `users/schemas.py`;
 * - `loc` terminando em índice numérico, dentro de uma lista.
 *
 * Nos três, `setError` era chamado para um nome que nenhum campo escuta e a mensagem
 * sumia — e, como `errors` vinha preenchido, o alerta geral também era suprimido. O
 * usuário clicava em Salvar e nada acontecia. Aqui, o que não casa com um campo vira
 * mensagem geral, que é sempre exibida. */
export interface ApiErrorSummary {
  fields: ServerFieldError[];
  /** Mensagens sem campo correspondente — precisam aparecer no alerta geral. */
  messages: string[];
}

/** `loc` do FastAPI é prefixado por "body"; sozinho, ele significa "o corpo inteiro". */
function fieldNameFromLoc(loc: unknown[]): string | null {
  const last = loc[loc.length - 1];
  if (typeof last !== "string" || last === "body") return null;
  return last;
}

export function describeApiErrors(error: ApiError): ApiErrorSummary {
  const summary: ApiErrorSummary = { fields: [], messages: [] };
  if (!Array.isArray(error.errors)) return summary;
  for (const item of error.errors) {
    if (typeof item === "string") {
      summary.messages.push(item);
      continue;
    }
    if (typeof item !== "object" || item === null || !("msg" in item)) continue;
    const message = String((item as { msg: unknown }).msg);
    const loc = (item as { loc?: unknown }).loc;
    const field = Array.isArray(loc) ? fieldNameFromLoc(loc) : null;
    if (field === null) {
      summary.messages.push(message);
    } else {
      summary.fields.push({ field, message });
    }
  }
  return summary;
}

/** Regra 4 da spec 007: erro de validação do servidor (422) mapeia para o campo
 * correspondente. Continua sendo a porta de entrada dos formulários que não usam
 * `FormModal` — o que não tem campo agora sai por `describeApiErrors`. */
export function mapApiErrorToFields(error: ApiError): ServerFieldError[] {
  return describeApiErrors(error).fields;
}

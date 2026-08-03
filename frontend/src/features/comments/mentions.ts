/** Detecção do token de `@menção` sob o cursor (spec 035) — função pura para o
 * CommentEditor e para os testes: devolve o início e o texto parcial da menção que
 * está sendo digitada, ou null quando o cursor não está num token `@...`. */

export interface MentionToken {
  /** Índice do `@` no texto. */
  start: number;
  /** Texto parcial depois do `@` até o cursor (a query do autocomplete). */
  query: string;
}

export function findMentionToken(text: string, cursor: number): MentionToken | null {
  const beforeCursor = text.slice(0, cursor);
  const atIndex = beforeCursor.lastIndexOf("@");
  if (atIndex < 0) {
    return null;
  }
  // O `@` precisa iniciar o texto ou vir depois de um separador — e-mail não é menção.
  if (atIndex > 0 && !/[\s([{]/.test(text[atIndex - 1] ?? "")) {
    return null;
  }
  const query = beforeCursor.slice(atIndex + 1);
  // Espaço + outro caractere depois encerra o token ("@Maria Silva, oi" → até a vírgula;
  // aceitamos espaços NO NOME, mas dois separadores seguidos encerram).
  if (/[.,;:!?\n]/.test(query)) {
    return null;
  }
  return { start: atIndex, query };
}

/** Substitui o token ativo pelo nome escolhido no autocomplete. */
export function applyMention(text: string, token: MentionToken, name: string): string {
  return `${text.slice(0, token.start)}@${name} ${text.slice(token.start + 1 + token.query.length)}`;
}

// Spec 138, regra 2: link de terceiro só é renderizado se o esquema for http/https.
//
// O `link` de uma publicação vem verbatim do DJEN (`integrations/djen/parser.py`) e o
// payload de sincronização é aceito de qualquer COLABORADOR; o React 18 renderiza
// `href="javascript:…"` sem reclamar. Aqui é o único lugar que decide se um endereço
// vindo de fora vira `href`/`window.open` — quem não passar não vira link nenhum.

const SAFE_SCHEMES = new Set(["http:", "https:", "mailto:", "tel:"]);

/** Endereço externo seguro, ou `undefined` quando o esquema não é permitido.
 *
 * Devolver `undefined` (e não string vazia) é proposital: `href={undefined}` faz o React
 * omitir o atributo, e um `<a>` sem `href` não é link nem para o teclado nem para o
 * leitor de tela — que é exatamente o que queremos para um endereço que não confiamos. */
export function safeExternalHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  const trimmed = url.trim();
  if (trimmed === "") return undefined;
  let parsed: URL;
  try {
    // Base explícita: sem ela, "javascript:alert(1)" continua sendo URL absoluta (e é
    // pega pelo teste de esquema abaixo), mas "/algum/caminho" jogaria exceção.
    parsed = new URL(trimmed, window.location.origin);
  } catch {
    return undefined;
  }
  if (!SAFE_SCHEMES.has(parsed.protocol)) return undefined;
  // Só endereço absoluto: um caminho relativo resolvido contra a nossa origem não é
  // "link externo", e mandá-lo para `window.open` confunde mais do que ajuda.
  return /^[a-z][a-z0-9+.-]*:/i.test(trimmed) ? parsed.href : undefined;
}

/** Abre um endereço externo em outra aba, sem `opener` e só se o esquema for seguro.
 * Devolve `false` quando recusou — quem chama decide o que dizer ao usuário. */
export function openExternal(url: string | null | undefined): boolean {
  const href = safeExternalHref(url);
  if (!href) return false;
  window.open(href, "_blank", "noopener,noreferrer");
  return true;
}

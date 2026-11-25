export interface SandboxedHtmlProps {
  /** HTML de origem não confiável. Nunca é injetado no documento da aplicação. */
  html: string;
  title: string;
  className?: string;
  /** Altura do quadro. O conteúdo rola dentro dele — ver a nota sobre altura abaixo. */
  height?: number;
  /** Repassado ao iframe: os testes das features identificam o quadro por ele. */
  "data-testid"?: string;
}

/** Folha de estilo mínima para o conteúdo ficar legível dentro do quadro. Vive aqui, e
 * não no CSS da aplicação, porque o iframe é um documento separado: nada do Tailwind
 * atravessa a fronteira (que é justamente o ponto). */
const FRAME_STYLES = `
  :root { color-scheme: light dark; }
  html, body { margin: 0; }
  body {
    font: 14px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 16px;
    color: #1f2937;
    background: transparent;
    word-wrap: break-word;
  }
  @media (prefers-color-scheme: dark) { body { color: #e5e7eb; } }
  table { border-collapse: collapse; max-width: 100%; }
  td, th { border: 1px solid currentColor; padding: 4px 8px; }
  img { max-width: 100%; height: auto; }
`;

/** Renderiza HTML de origem não confiável **isolado do documento da aplicação**.
 *
 * Spec 138, regra 1. O caminho que motivou o componente: o texto de uma minuta é escrito
 * por um modelo de linguagem e gravado cru pelo backend (`legal_agents/service.py`); o
 * guarda-corpo de citações troca números de súmula e **não é sanitizador**. Renderizar
 * isso com `dangerouslySetInnerHTML` põe HTML de terceiro dentro da nossa origem, onde
 * mora o refresh token de 30 dias (`lib/api.ts`).
 *
 * Por que um `<iframe sandbox srcdoc>` e não uma biblioteca de sanitização: sem
 * `allow-scripts` o navegador não executa script nenhum dentro do quadro — nem `<script>`,
 * nem `onerror=`, nem `javascript:` — e sem `allow-same-origin` o documento fica numa
 * origem opaca, sem acesso ao `localStorage`, aos cookies nem ao DOM da aplicação. É uma
 * garantia do navegador, não uma lista de tags que alguém precisa manter atualizada — e
 * escrever a lista à mão seria justamente o falso conforto que a auditoria pediu para
 * evitar. `allow-popups`/`allow-forms`/`allow-top-navigation` também ficam de fora: nada
 * ali dentro navega, envia formulário ou abre janela.
 *
 * O preço é a altura fixa: origem opaca significa que o pai não consegue medir o
 * conteúdo do quadro para se ajustar a ele. O conteúdo rola dentro do quadro, e quem
 * quiser editar de verdade abre no editor de modelos — que é o botão ao lado. */
export function SandboxedHtml({
  html,
  title,
  className,
  height = 384,
  "data-testid": testId,
}: SandboxedHtmlProps): JSX.Element {
  const srcDoc = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>${FRAME_STYLES}</style></head><body>${html}</body></html>`;
  return (
    <iframe
      title={title}
      sandbox=""
      referrerPolicy="no-referrer"
      srcDoc={srcDoc}
      style={{ height }}
      className={className}
      data-testid={testId}
    />
  );
}

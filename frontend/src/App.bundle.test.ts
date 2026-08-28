/**
 * Spec 098, regra 7 — o editor e os gráficos ficam FORA do bundle inicial.
 *
 * Este teste não mede bytes: medir exige um build de produção, que leva mais tempo que
 * os 279 testes de front-end somados e não caberia no orçamento de 300 s do `make test`.
 * O número é verificado por `npm run bundle:check`, depois do build, no CI.
 *
 * O que se garante aqui é a propriedade ESTRUTURAL da qual o número depende: nenhuma
 * página de feature é importada estaticamente pelo `App.tsx`. É essa propriedade que
 * quebra primeiro — basta um `import { ReportsPage } from ...` acrescentado sem pensar
 * para o TipTap e os gráficos voltarem para o chunk que todo mundo baixa no login.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// `import.meta.url` no ambiente jsdom do Vitest não é `file:` — o caminho vem do cwd,
// que o Vitest fixa na raiz do pacote.
const APP = readFileSync(join(process.cwd(), "src", "App.tsx"), "utf8");

/** A única página que pode ser estática: é a primeira tela de todo mundo, e adiar o
 * carregamento dela seria mudar o problema de lugar em vez de resolvê-lo. */
const ESTATICAS_PERMITIDAS = ["@/features/auth/LoginPage"];

describe("bundle inicial (spec 098, regra 7)", () => {
  it("nenhuma página de feature entra por import estático", () => {
    const estaticos = [...APP.matchAll(/^import .* from "(@\/features\/[^"]+)";$/gm)].map(
      (m) => m[1],
    );

    expect(estaticos).toEqual(ESTATICAS_PERMITIDAS);
  });

  it("editor e relatórios entram por import dinâmico", () => {
    const dinamicos = [...APP.matchAll(/await import\("(@\/features\/[^"]+)"\)/g)].map((m) => m[1]);

    expect(dinamicos).toContain("@/features/templates/TemplateEditorPage");
    expect(dinamicos).toContain("@/features/reports/ReportsPage");
  });

  it("as rotas ficam dentro de um Suspense", () => {
    // `lazy` sem `Suspense` não é code splitting, é uma tela branca com erro no console.
    expect(APP).toMatch(/<Suspense fallback=/);
  });
});

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";

// Spec 102: esta lista era uma CÓPIA MANUAL do menu — e omitia justamente Financeiro,
// Configurações e Conta e assinatura, os três itens com `capability`. Foi por isso que o
// `/settings` quebrado sobreviveu 92 specs a uma jornada chamada "navegar por todos os
// módulos": ela não passava por ele.
//
// Agora a lista é DERIVADA de `navItems.ts`. Lê-se o arquivo em vez de importá-lo porque
// `navItems.ts` importa ícones de `lucide-react`, que é dependência do frontend e não do
// pacote e2e — o import resolveria no editor e quebraria na execução.
function routableNavItems(): { path: string; label: string }[] {
  const fonte = readFileSync(
    resolve(
      fileURLToPath(new URL(".", import.meta.url)),
      "../../frontend/src/components/shell/navItems.ts",
    ),
    "utf-8",
  );
  // Cada entrada é `{ label: "X", path: "/y", ... }`; itens sem `path` abrem modal e não
  // navegam (Suporte, Indicar), então ficam de fora — é o mesmo filtro do
  // ROUTABLE_NAV_ITEMS exportado pelo arquivo.
  const itens = [
    ...fonte.matchAll(
      /label:\s*"([^"]+)",\s*(?:\/\/[^\n]*\n\s*)*path:\s*"([^"]+)"/g,
    ),
  ];
  return itens.map(([, label, path]) => ({
    label: label as string,
    path: path as string,
  }));
}

const ROUTABLE_MODULES = routableNavItems();

/** Rotas do menu que redirecionam para outro lugar — a jornada espera o DESTINO. */
const REDIRECTS: Record<string, string> = {
  "/posts": "/home",
};

test("jornada 2/25: navegar por todos os módulos da sidebar", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page).toHaveURL(/\/home/);

  // Guarda contra a regex silenciosamente parar de casar: se ela devolvesse [], o laço
  // abaixo não rodaria e a jornada passaria sem testar nada.
  expect(ROUTABLE_MODULES.length).toBeGreaterThanOrEqual(13);

  for (const item of ROUTABLE_MODULES) {
    await page
      .getByRole("navigation", { name: "Navegação principal" })
      .getByRole("link", { name: item.label })
      .click();
    // Alguns itens apontam para uma rota que redireciona (spec 102: /posts vai para o
    // painel enquanto a listagem de atividades não existe — dívida nº 26). Esperar a URL
    // de ORIGEM aqui seria uma corrida contra o redirect do React Router.
    const destino = REDIRECTS[item.path] ?? item.path;
    await expect(page).toHaveURL(new RegExp(destino.replace(/\//g, "\\/")));
    // O que a jornada realmente garante: nenhum item do menu cai no NotFoundPage.
    await expect(page.getByText("Página não encontrada.")).toBeHidden();
  }

  await page.goto("/rota-que-nao-existe");
  await expect(page.getByText("Página não encontrada.")).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Navegação principal" }),
  ).toBeVisible();
});

import { expect, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";

const ROUTABLE_MODULES: { path: string; label: string }[] = [
  { path: "/home", label: "Meu Painel" },
  { path: "/schedules", label: "Agenda" },
  { path: "/posts", label: "Atividades" },
  { path: "/crm", label: "CRM" },
  { path: "/customers", label: "Contatos" },
  { path: "/lawsuits", label: "Processos" },
  { path: "/publications", label: "Intimações" },
  { path: "/partners", label: "Parceiros" },
  { path: "/library", label: "Modelos" },
  { path: "/reports", label: "Relatórios" },
];

test("jornada 2/25: navegar por todos os módulos da sidebar", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page).toHaveURL(/\/home/);

  for (const item of ROUTABLE_MODULES) {
    await page.getByRole("navigation", { name: "Navegação principal" }).getByRole("link", { name: item.label }).click();
    await expect(page).toHaveURL(new RegExp(item.path.replace("/", "\\/")));
  }

  await page.goto("/rota-que-nao-existe");
  await expect(page.getByText("Página não encontrada.")).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Navegação principal" }),
  ).toBeVisible();
});

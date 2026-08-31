import { expect, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";

test("jornada 3/25: contato — criar → filtrar → editar → arquivar", async ({
  page,
}) => {
  const name = `Contato E2E ${Date.now()}`;
  const updatedName = `${name} (editado)`;

  await page.goto("/login");
  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/home/);

  await page
    .getByRole("navigation", { name: "Navegação principal" })
    .getByRole("link", { name: "Contatos" })
    .click();
  await expect(page).toHaveURL(/\/customers/);

  // criar
  await page.getByRole("button", { name: "Novo contato" }).click();
  await page.getByLabel("Nome", { exact: true }).fill(name);
  await page.getByLabel("Origem da pessoa").fill("Indic");
  await page.getByRole("option", { name: "INDICAÇÃO" }).click();
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  // filtrar
  await page.getByLabel("Buscar").fill(name);
  await expect(page.getByText(name, { exact: true })).toBeVisible();

  // editar
  const row = page.getByRole("row", { name });
  await row.getByRole("button", { name: "Editar" }).click();
  await page.getByLabel("Nome", { exact: true }).fill(updatedName);
  await page.getByRole("button", { name: "Salvar" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  await page.getByLabel("Buscar").fill(updatedName);
  await expect(page.getByText(updatedName, { exact: true })).toBeVisible();

  // arquivar
  const updatedRow = page.getByRole("row", { name: updatedName });
  await updatedRow.getByRole("button", { name: "Arquivar" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Arquivar" })
    .click();
  await expect(page.getByRole("dialog")).toBeHidden();

  await page.getByLabel("Arquivados").selectOption("true");
  await expect(page.getByText(updatedName, { exact: true })).toBeVisible();
});

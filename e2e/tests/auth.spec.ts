import { expect, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";

test("jornada 1/25: login → home → logout", async ({ page }) => {
  await page.goto("/login");

  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();

  await expect(page.getByText(/bem-vindo/i)).toBeVisible();

  await page.getByRole("button", { name: "Sair" }).click();

  await expect(page).toHaveURL(/\/login/);
});

import { expect, request, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";
const API_BASE_URL = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** "R$ 1.050,00" → 1050 — o tenant e2e nunca reseta entre execuções (CLAUDE.md/e2e), então
 * o card "Receita" acumula lançamentos de rodadas anteriores; a jornada compara antes/depois
 * em vez de esperar um valor absoluto. */
function parseBrl(text: string): number {
  const normalized = text
    .replace(/[^0-9.,-]/g, "")
    .replace(/\./g, "")
    .replace(",", ".");
  return Number(normalized);
}

test("jornada 9/25: financeiro — criar receita → baixar → ver no dashboard", async ({
  page,
}) => {
  const suffix = Date.now();
  const categoryName = `Categoria E2E ${suffix}`;
  const costCenterName = `Centro E2E ${suffix}`;
  const accountName = `Conta E2E ${suffix}`;

  // ---- setup via API (categoria/centro/conta são pré-condições, não o alvo da jornada —
  // a migration 054 só semeia essas tabelas para tenants que já existiam quando ela rodou,
  // e o tenant e2e nasce depois, mesma situação de customer_origins/016 em seed_e2e.py)
  const api = await request.newContext({ baseURL: API_BASE_URL });
  const loginResponse = await api.post("/api/v1/auth/login", {
    headers: { "X-Tenant-Id": TENANT_ID },
    data: { email: EMAIL, password: PASSWORD },
  });
  expect(loginResponse.ok()).toBeTruthy();
  const { access_token: accessToken } = await loginResponse.json();
  const headers = {
    "X-Tenant-Id": TENANT_ID,
    Authorization: `Bearer ${accessToken}`,
  };

  const category = await (
    await api.post("/api/v1/financial-categories", {
      headers,
      data: { name: categoryName, type: "RECEITA", dre_group_id: 1 },
    })
  ).json();
  expect(category.id).toBeTruthy();
  const costCenter = await (
    await api.post("/api/v1/cost-centers", {
      headers,
      data: { name: costCenterName },
    })
  ).json();
  expect(costCenter.id).toBeTruthy();
  const account = await (
    await api.post("/api/v1/bank-accounts", {
      headers,
      data: { kind: "CORRENTE", name: accountName, initial_amount: "0" },
    })
  ).json();
  expect(account.id).toBeTruthy();

  // ---- jornada na UI: login → /transactions → novo lançamento
  await page.goto("/login");
  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/home/);

  await page
    .getByRole("navigation", { name: "Navegação principal" })
    .getByRole("link", { name: "Financeiro" })
    .click();
  await expect(page).toHaveURL(/\/transactions/);

  const dashboard = page.getByRole("region", { name: "Painel financeiro" });
  const receitaCard = dashboard
    .getByText("Receita", { exact: true })
    .locator("..");
  const receitaBefore = parseBrl(
    (await receitaCard.locator(".text-2xl").innerText()) ?? "0",
  );

  await page.getByRole("button", { name: "Novo lançamento" }).click();
  const dialog = page.getByRole("dialog");

  await dialog.getByLabel("Conta", { exact: true }).fill(accountName);
  await page.getByRole("option", { name: accountName }).click();

  await dialog.getByPlaceholder("Buscar categoria…").fill(categoryName);
  await page.getByRole("option", { name: categoryName }).click();

  await dialog.getByLabel("Centro de custo").fill(costCenterName);
  await page.getByRole("option", { name: costCenterName }).click();

  await dialog.getByLabel("Valor").fill("350,00");
  await dialog
    .getByLabel("Vencimento")
    .fill(new Date().toISOString().slice(0, 10));

  await dialog.getByRole("button", { name: "Salvar" }).click();
  await expect(dialog).toBeHidden();

  // ---- baixar o lançamento recém-criado
  const row = page.getByRole("row", { name: categoryName });
  await row.getByRole("button", { name: "Baixar" }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Confirmar" })
    .click();
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(row.getByText(/Pago em/)).toBeVisible();

  // ---- o card "Receita" do dashboard reflete o lançamento pago (regra 4: realizado =
  // com payment_date preenchida) — cresce exatamente 350 em relação ao valor antes da
  // jornada. O card "Saldo" depende da view materializada (regra 6/11), que só um
  // worker fora do escopo do e2e atualiza — não verificado aqui.
  await expect(async () => {
    const receitaAfter = parseBrl(
      (await receitaCard.locator(".text-2xl").innerText()) ?? "0",
    );
    expect(receitaAfter).toBe(receitaBefore + 350);
  }).toPass({ timeout: 5_000 });
});

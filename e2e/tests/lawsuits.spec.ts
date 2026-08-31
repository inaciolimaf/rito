import { expect, request, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";
const API_BASE_URL = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

test("jornada 4/25: processo — criar → filtrar por visão → abrir timeline", async ({
  page,
}) => {
  const suffix = Date.now();
  const customerName = `Cliente E2E ${suffix}`;

  // ---- setup via API (grupo/tipo/etapa/contato são pré-condições, não o alvo da jornada)
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

  const group = await (
    await api.post("/api/v1/action-groups", {
      headers,
      data: { name: `Grupo E2E ${suffix}` },
    })
  ).json();
  await api.post("/api/v1/lawsuit-types", {
    headers,
    data: { name: `Tipo E2E ${suffix}`, action_group_id: group.id },
  });
  await api.post("/api/v1/stages", {
    headers,
    data: { name: `Etapa E2E ${suffix}`, step_id: 1 },
  });
  const origins = await (
    await api.get("/api/v1/customer-origins", { headers })
  ).json();
  const customer = await (
    await api.post("/api/v1/customers", {
      headers,
      data: { type: "PF", name: customerName, origin_id: origins.items[0].id },
    })
  ).json();
  expect(customer.id).toBeTruthy();

  // ---- jornada na UI: login → /lawsuits → novo processo
  await page.goto("/login");
  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/home/);

  await page.goto("/lawsuits");
  await page.getByRole("button", { name: "Novo processo" }).click();
  const dialog = page.getByRole("dialog");

  await dialog.getByLabel("Responsável").fill("Usuário E2E");
  await page.getByRole("option", { name: "Usuário E2E" }).click();

  await dialog
    .getByLabel("Grupo de ação")
    .selectOption({ label: `Grupo E2E ${suffix}` });
  await dialog
    .getByLabel("Tipo de ação")
    .selectOption({ label: `Tipo E2E ${suffix}` });

  await dialog.getByLabel("Fase").selectOption({ label: "Marketing" });
  await dialog
    .getByLabel("Etapa")
    .selectOption({ label: `Etapa E2E ${suffix}` });

  await dialog.getByLabel("Adicionar partes envolvidas").fill(customerName);
  await page.getByRole("option", { name: customerName }).click();

  await dialog.getByRole("button", { name: "Salvar" }).click();
  await expect(dialog).toBeHidden();

  // ---- filtrar por visão e localizar o processo na listagem
  await page.getByLabel("Visão").selectOption("active");
  await expect(page).toHaveURL(/view=active/);
  await expect(page.getByText(customerName)).toBeVisible();

  // ---- abrir o detalhe: a timeline é a tela principal
  await page.getByRole("button", { name: "Abrir" }).first().click();
  await expect(page).toHaveURL(/\/lawsuits\/[0-9a-f-]{36}/);
  await expect(
    page.getByRole("button", { name: "Nova movimentação" }),
  ).toBeVisible();
});

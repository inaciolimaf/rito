import { expect, request, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";
const API_BASE_URL = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

test("jornada 5/25: criar tarefa → aparece na caixa de entrada → concluir em massa", async ({
  page,
}) => {
  const suffix = Date.now();

  // ---- setup via API (processo + tarefa são pré-condições, não o alvo da jornada)
  const api = await request.newContext({ baseURL: API_BASE_URL });
  const loginResponse = await api.post("/api/v1/auth/login", {
    headers: { "X-Tenant-Id": TENANT_ID },
    data: { email: EMAIL, password: PASSWORD },
  });
  expect(loginResponse.ok()).toBeTruthy();
  const { access_token: accessToken } = await loginResponse.json();
  const headers = { "X-Tenant-Id": TENANT_ID, Authorization: `Bearer ${accessToken}` };

  const group = await (
    await api.post("/api/v1/action-groups", { headers, data: { name: `Grupo E2E ${suffix}` } })
  ).json();
  const lawsuitType = await (
    await api.post("/api/v1/lawsuit-types", {
      headers,
      data: { name: `Tipo E2E ${suffix}`, action_group_id: group.id },
    })
  ).json();
  const stage = await (
    await api.post("/api/v1/stages", { headers, data: { name: `Etapa E2E ${suffix}`, step_id: 1 } })
  ).json();
  const origins = await (await api.get("/api/v1/customer-origins", { headers })).json();
  const customer = await (
    await api.post("/api/v1/customers", {
      headers,
      data: { type: "PF", name: `Cliente E2E ${suffix}`, origin_id: origins.items[0].id },
    })
  ).json();
  const me = await (await api.get("/api/v1/auth/me", { headers })).json();
  const lawsuit = await (
    await api.post("/api/v1/lawsuits", {
      headers,
      data: {
        user_id: me.id,
        lawsuit_type_id: lawsuitType.id,
        stage_id: stage.id,
        parties: [{ customer_id: customer.id, pole: "ATIVO", is_client: true }],
      },
    })
  ).json();
  const taskTypeName = `Tarefa E2E ${suffix}`;
  const taskType = await (
    await api.post("/api/v1/task-types", { headers, data: { name: taskTypeName, reward: 5 } })
  ).json();
  const post = await (
    await api.post("/api/v1/posts", {
      headers,
      data: {
        lawsuit_id: lawsuit.id,
        task_type_id: taskType.id,
        user_ids: [me.id],
        scheduled_date: new Date().toISOString().slice(0, 10),
      },
    })
  ).json();
  expect(post.id).toBeTruthy();

  // ---- jornada na UI: login → /home → a tarefa está em "Não lidas"
  await page.goto("/login");
  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/home/);

  await expect(page.getByRole("link", { name: taskTypeName })).toBeVisible();

  // ---- concluir em massa: selecionar → Concluir → a tarefa sai da caixa
  await page.getByLabel(`Selecionar ${taskTypeName}`).check();
  await page.getByRole("button", { name: "Concluir" }).click();
  await expect(page.getByRole("link", { name: taskTypeName })).toBeHidden();
});

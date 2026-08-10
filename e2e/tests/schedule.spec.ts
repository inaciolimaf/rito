import { expect, request, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";
const API_BASE_URL = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

test("jornada 6/25: criar compromisso na agenda → ver no mês → abrir", async ({ page }) => {
  const suffix = Date.now();

  // ---- setup via API (processo, tipo de tarefa e usuário são pré-condições)
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
  const customerName = `Cliente Agenda ${suffix}`;
  const customer = await (
    await api.post("/api/v1/customers", {
      headers,
      data: { type: "PF", name: customerName, origin_id: origins.items[0].id },
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
  const taskTypeName = `Compromisso E2E ${suffix}`;
  const taskType = await (
    await api.post("/api/v1/task-types", { headers, data: { name: taskTypeName, reward: 5 } })
  ).json();

  // ---- jornada na UI: login → /schedules → clicar no dia de hoje
  await page.goto("/login");
  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/home/);

  await page.goto("/schedules");
  // Vai para o PRÓXIMO mês e clica no dia 15: o tenant de e2e acumula tarefas de
  // runs anteriores, e clicar num dia que já tem chip abriria a tarefa em vez do
  // formulário (o chip fica no centro da célula).
  await page.getByRole("button", { name: "Próximo →" }).click();
  const now = new Date();
  const target = new Date(now.getFullYear(), now.getMonth() + 1, 15);
  const targetIso = `${target.getFullYear()}-${String(target.getMonth() + 1).padStart(2, "0")}-15`;
  // Higiene de re-run (spec 041, descobertas): a visão mês mostra só 3 chips por dia
  // (MAX_VISIBLE do MonthView) e cada run acumula uma tarefa neste dia — sem limpar,
  // o chip novo cai atrás do "+N mais" e a jornada falha de forma intermitente.
  const dayEvents = await (
    await api.get(`/api/v1/schedule?from=${targetIso}&to=${targetIso}`, { headers })
  ).json();
  for (const event of dayEvents.items as { post_id: string; task_type_name: string }[]) {
    if (event.task_type_name.startsWith("Compromisso E2E")) {
      await api.delete(`/api/v1/posts/${event.post_id}`, { headers });
    }
  }
  // Clique no canto superior esquerdo (no número do dia), não no centro: com tarefas
  // acumuladas de runs anteriores, o centro da célula cai num chip e abre a tarefa em
  // vez do formulário (flake de re-run dentro do mesmo mês — spec 039, descobertas).
  await page.getByTestId(`day-cell-${targetIso}`).click({ position: { x: 8, y: 8 } });

  // ---- o modal abre com a data preenchida (regra 7); completar e criar
  await expect(page.locator("#post-date")).toHaveValue(targetIso);
  await page.getByPlaceholder("Buscar por cliente ou número…").fill(customerName);
  await page.getByRole("option", { name: new RegExp(customerName) }).click();
  await page.getByLabel("Tarefa", { exact: true }).selectOption({ label: `${taskTypeName} (5 pts)` });
  await page.getByPlaceholder("Quem vai trabalhar nesta tarefa?").fill(me.name);
  await page.getByRole("option", { name: new RegExp(me.name) }).click();
  await page.getByRole("button", { name: "Salvar" }).click();

  // ---- o compromisso aparece na visão mês; clicar abre o detalhe da tarefa
  const chip = page.getByTestId("schedule-event").filter({ hasText: taskTypeName });
  await expect(chip).toBeVisible();
  await chip.click();
  await expect(page).toHaveURL(/\/posts\//);
  await expect(page.getByText(taskTypeName).first()).toBeVisible();
});

import { expect, request, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";
const API_BASE_URL = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

test("jornada 7/25: intimação chega → vincular → tarefa criada", async ({
  page,
}) => {
  const suffix = Date.now();

  // ---- setup via API (processo, tipo sistêmico e a publicação "chegando" são pré-condições)
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
      data: { name: `Grupo Intimação ${suffix}` },
    })
  ).json();
  const lawsuitType = await (
    await api.post("/api/v1/lawsuit-types", {
      headers,
      data: { name: `Tipo Intimação ${suffix}`, action_group_id: group.id },
    })
  ).json();
  const stage = await (
    await api.post("/api/v1/stages", {
      headers,
      data: { name: `Etapa Intimação ${suffix}`, step_id: 1 },
    })
  ).json();
  const origins = await (
    await api.get("/api/v1/customer-origins", { headers })
  ).json();
  const customerName = `Cliente Intimação ${suffix}`;
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

  // Tipo sistêmico que o roteamento da spec 045 usa — cria só se ainda não existir
  // neste tenant (runs anteriores já podem tê-lo criado).
  const existingTypes = await (
    await api.get("/api/v1/task-types?q=Intimações Judiciais", { headers })
  ).json();
  if (
    !existingTypes.items.some(
      (item: { name: string }) => item.name === "Intimações Judiciais",
    )
  ) {
    await api.post("/api/v1/task-types", {
      headers,
      data: { name: "Intimações Judiciais", reward: 5 },
    });
  }

  // Regra 8 (spec 048): sem NENHUM termo monitorado, a tela mostra o estado
  // vazio em vez da lista — o tenant de e2e precisa de pelo menos um.
  const existingTerms = await (
    await api.get("/api/v1/monitored-terms", { headers })
  ).json();
  if (existingTerms.total === 0) {
    await api.post("/api/v1/monitored-terms", {
      headers,
      data: { kind: "OAB", value: "999999", oab_state: "SP" },
    });
  }

  const organName = `Vara Intimação ${suffix}`;
  const publicationResponse = await api.post("/api/v1/publications", {
    headers,
    data: {
      item: {
        // external_id é INTEGER (32 bits) no banco (spec 042) — milissegundos
        // (Date.now()) estoura; segundos cabe com folga e ainda é único o
        // bastante pra este teste.
        id: Math.floor(suffix / 1000),
        hash: `e2e-publications-${suffix}`,
        data_disponibilizacao: new Date().toISOString().slice(0, 10),
        siglaTribunal: "TJSP",
        nomeOrgao: organName,
        tipoComunicacao: "Intimação",
        texto: `Texto da intimação de teste e2e ${suffix}.`,
      },
    },
  });
  expect(publicationResponse.ok()).toBeTruthy();
  const publication = await publicationResponse.json();
  expect(publication.lawsuit_id).toBeNull(); // chega sem processo — regra 6 da 045

  // ---- jornada na UI: login → /publications → localizar a intimação → vincular
  await page.goto("/login");
  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/home/);

  await page.goto("/publications");
  const row = page.locator("tr", { hasText: organName });
  await expect(row).toBeVisible();
  await expect(row.getByText("Não vinculada")).toBeVisible();

  await row.getByRole("button", { name: "Vincular" }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByPlaceholder("Buscar por cliente ou número…")
    .fill(customerName);
  await page.getByRole("option", { name: new RegExp(customerName) }).click();
  await dialog.getByRole("button", { name: "Vincular", exact: true }).click();

  // ---- a linha atualiza para "Vinculada" e a tarefa da spec 045 foi criada
  await expect(row.getByText("Vinculada")).toBeVisible();

  await expect(async () => {
    const posts = await (
      await api.get(`/api/v1/lawsuits/${lawsuit.id}/posts`, { headers })
    ).json();
    const createdTask = posts.find(
      (post: { task_type_name: string }) =>
        post.task_type_name === "Intimações Judiciais",
    );
    expect(createdTask).toBeTruthy();
    expect(createdTask.scheduled_date).toBe(publication.availability_date);
  }).toPass({ timeout: 5_000 });
});

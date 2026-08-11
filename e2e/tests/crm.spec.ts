import { expect, request, test } from "@playwright/test";

const TENANT_ID = "00000000-0000-0000-0000-0000000000e2";
const EMAIL = "e2e@rito.app";
const PASSWORD = "SenhaE2E123!";
const API_BASE_URL = process.env.VITE_API_BASE_URL ?? "http://localhost:8000";

test("jornada 8/25: CRM — arrastar card no Kanban muda a fase", async ({
  page,
}) => {
  const suffix = Date.now();

  // ---- setup via API: processo na fase Marketing (step 1) + uma etapa em Negociação (step 2)
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
      data: { name: `Grupo CRM ${suffix}` },
    })
  ).json();
  const lawsuitType = await (
    await api.post("/api/v1/lawsuit-types", {
      headers,
      data: { name: `Tipo CRM ${suffix}`, action_group_id: group.id },
    })
  ).json();
  const marketingStage = await (
    await api.post("/api/v1/stages", {
      headers,
      data: { name: `Marketing CRM ${suffix}`, step_id: 1 },
    })
  ).json();
  await api.post("/api/v1/stages", {
    headers,
    data: { name: `Negociação CRM ${suffix}`, step_id: 2 },
  });
  const origins = await (
    await api.get("/api/v1/customer-origins", { headers })
  ).json();
  const customerName = `Cliente CRM ${suffix}`;
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
        stage_id: marketingStage.id,
        parties: [{ customer_id: customer.id, pole: "ATIVO", is_client: true }],
      },
    })
  ).json();

  // ---- jornada na UI: login → /crm → arrastar o card de Marketing para Negociação
  await page.goto("/login");
  await page.getByLabel("ID do escritório").fill(TENANT_ID);
  await page.getByLabel("E-mail").fill(EMAIL);
  await page.getByLabel("Senha").fill(PASSWORD);
  await page.getByRole("button", { name: "Entrar" }).click();
  await expect(page).toHaveURL(/\/home/);

  await page.goto("/crm");
  const card = page.getByTestId(`kanban-card-${lawsuit.id}`);
  await expect(card).toBeVisible();
  const negotiationColumn = page.getByTestId("kanban-column-2");
  const marketingColumn = page.getByTestId("kanban-column-1");
  await expect(
    marketingColumn.locator(`[data-testid="kanban-card-${lawsuit.id}"]`),
  ).toBeVisible();

  // Playwright's dragTo() simula o mouse, mas o drag&drop nativo HTML5 (spec 051) nem
  // sempre nasce de um gesto de mouse simulado em CI headless — dispara os eventos DOM
  // diretamente com um DataTransfer real. Intermitente ocasionalmente (mesma classe de
  // corrida já vista na jornada 7/25, spec 048): repete o gesto até o card aparecer na
  // coluna de destino em vez de confiar numa única tentativa (retry por condição).
  await expect(async () => {
    await page.evaluate(
      ({ sourceId, targetId }) => {
        const source = document.querySelector(`[data-testid="${sourceId}"]`);
        const target = document.querySelector(`[data-testid="${targetId}"]`);
        if (!source || !target)
          throw new Error("drag source/target não encontrados");
        const dataTransfer = new DataTransfer();
        source.dispatchEvent(
          new DragEvent("dragstart", { bubbles: true, dataTransfer }),
        );
        target.dispatchEvent(
          new DragEvent("dragover", {
            bubbles: true,
            cancelable: true,
            dataTransfer,
          }),
        );
        target.dispatchEvent(
          new DragEvent("drop", {
            bubbles: true,
            cancelable: true,
            dataTransfer,
          }),
        );
        source.dispatchEvent(
          new DragEvent("dragend", { bubbles: true, dataTransfer }),
        );
      },
      { sourceId: `kanban-card-${lawsuit.id}`, targetId: "kanban-column-2" },
    );
    await expect(
      negotiationColumn.locator(`[data-testid="kanban-card-${lawsuit.id}"]`),
    ).toBeVisible({ timeout: 1_000 });
  }).toPass({ timeout: 10_000 });

  // ---- o processo persistiu a mudança de fase no banco
  await expect(async () => {
    const updated = await (
      await api.get(`/api/v1/lawsuits/${lawsuit.id}`, { headers })
    ).json();
    expect(updated.step_id).toBe(2);
  }).toPass({ timeout: 5_000 });
});

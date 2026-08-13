import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationSettingsPage } from "@/features/notifications/NotificationSettingsPage";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

let currentRole = "GESTOR";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "user-1", role: currentRole } }),
}));

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/settings/notifications"]}>
        <NotificationSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const RULES = [
  { event: "NOVO_CLIENTE", responsible_user_id: null, channels: [] },
  { event: "NOVO_PROCESSO", responsible_user_id: null, channels: [] },
  { event: "INTIMACAO", responsible_user_id: null, channels: [] },
];

const PREFERENCES = [
  { channel: "EMAIL", enabled: true },
  { channel: "SMS", enabled: true },
  { channel: "WHATSAPP", enabled: true },
];

describe("NotificationSettingsPage", () => {
  afterEach(() => {
    server.resetHandlers();
    currentRole = "GESTOR";
  });

  it("gestor vê as regras dos 3 eventos e as próprias preferências", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/notification-rules`, () => HttpResponse.json(RULES)),
      http.get(`${BASE_URL}/api/v1/notification-preferences`, () => HttpResponse.json(PREFERENCES)),
      http.get(`${BASE_URL}/api/v1/users`, () =>
        HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
      ),
    );

    renderPage();

    expect(await screen.findByText("Novo contato")).toBeInTheDocument();
    expect(screen.getByText("Novo processo")).toBeInTheDocument();
    expect(screen.getByText("Intimação roteada")).toBeInTheDocument();
    expect(screen.getByText("Minhas preferências")).toBeInTheDocument();
    expect(screen.getAllByText("E-mail")).toHaveLength(1 + 3); // 1 checkbox de preferência + 3 de canal por regra
  });

  it("colaborador não vê a seção de regras, só as próprias preferências", async () => {
    currentRole = "COLABORADOR";
    server.use(
      http.get(`${BASE_URL}/api/v1/notification-preferences`, () => HttpResponse.json(PREFERENCES)),
    );

    renderPage();

    expect(await screen.findByText("Minhas preferências")).toBeInTheDocument();
    expect(screen.queryByText("Regras por evento")).not.toBeInTheDocument();
  });

  it("desligar um canal chama o PUT de preferência", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/notification-rules`, () => HttpResponse.json(RULES)),
      http.get(`${BASE_URL}/api/v1/notification-preferences`, () => HttpResponse.json(PREFERENCES)),
      http.get(`${BASE_URL}/api/v1/users`, () =>
        HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
      ),
    );
    let putBody: unknown = null;
    server.use(
      http.put(`${BASE_URL}/api/v1/notification-preferences/EMAIL`, async ({ request }) => {
        putBody = await request.json();
        return HttpResponse.json({ channel: "EMAIL", enabled: false });
      }),
    );

    const user = userEvent.setup();
    renderPage();

    const preferenceSection = screen.getByRole("region", { name: "Minhas preferências" });
    const emailCheckbox = await within(preferenceSection).findByRole("checkbox", {
      name: "E-mail",
    });
    await user.click(emailCheckbox);

    expect(putBody).toEqual({ enabled: false });
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UsersSettingsPage } from "@/features/users/UsersSettingsPage";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "admin-1", role: "GESTOR" } }),
}));

function renderPage(initialEntry = "/settings/users"): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <UsersSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("UsersSettingsPage", () => {
  afterEach(() => server.resetHandlers());

  it("alterna entre as abas Colaboradores e Times (ADVBOX: mesma tela, duas abas)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/occupations`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/api/v1/users`, () =>
        HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
      ),
      http.get(`${BASE_URL}/api/v1/squads`, () =>
        HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { name: "Usuários" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Times" }));

    expect(await screen.findByRole("heading", { name: "Times" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Times" })).toHaveAttribute("aria-selected", "true");
  });

  it("abre direto na aba Times quando a URL já tem ?tab=squads", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/occupations`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/api/v1/users`, () =>
        HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
      ),
      http.get(`${BASE_URL}/api/v1/squads`, () =>
        HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
      ),
    );

    renderPage("/settings/users?tab=squads");

    expect(await screen.findByRole("heading", { name: "Times" })).toBeInTheDocument();
  });
});

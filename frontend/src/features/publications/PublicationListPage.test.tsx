import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";
import { PublicationListPage } from "@/features/publications/PublicationListPage";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "gestor-1", role: "GESTOR" } }),
}));

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/publications"]}>
        <PublicationListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PublicationListPage", () => {
  afterEach(() => server.resetHandlers());

  it("sem termo monitorado cadastrado mostra estado vazio explicativo (regra 8)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/monitored-terms`, () =>
        HttpResponse.json({ items: [], total: 0 }),
      ),
      http.get(`${BASE_URL}/api/v1/publications`, () =>
        HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
      ),
      http.get(`${BASE_URL}/api/v1/publications/counts`, () =>
        HttpResponse.json({ total: 0, unlinked: 0, cancelled: 0, unread: 0 }),
      ),
    );

    renderPage();

    expect(await screen.findByText("Nenhum termo monitorado cadastrado")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Configurar termos monitorados" }),
    ).toBeInTheDocument();
  });
});

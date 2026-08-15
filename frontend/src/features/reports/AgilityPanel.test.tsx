import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgilityPanel } from "@/features/reports/AgilityPanel";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1", role: "ADMINISTRADOR" } }),
}));

function renderPanel(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AgilityPanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AgilityPanel", () => {
  afterEach(() => server.resetHandlers());

  it("mostra em dia / em atraso / pendentes e as listas de mais atrasados (spec 071 §8)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/reports/agility`, () =>
        HttpResponse.json({
          on_time: 4,
          late: 1,
          pending: 2,
          avg_days_to_complete: 1.5,
          avg_delay_days: 2.0,
          staleness_hint: "Pode levar até 15 min para refletir mudanças recentes.",
        }),
      ),
      http.get(`${BASE_URL}/api/v1/reports/most-delayed`, () =>
        HttpResponse.json({
          tasks: [
            {
              post_id: "p1",
              task_type_name: "Petição inicial",
              user_name: "Ana Advogada",
              lawsuit_folder: "Pasta 1",
              deadline_date: "2026-08-10",
              completed_at_date: "2026-08-12",
              delay_days: 2,
            },
          ],
          users: [
            { user_id: "u2", user_name: "Bruno Estagiário", late_count: 3, avg_delay_days: 1.7 },
          ],
        }),
      ),
    );

    renderPanel();

    expect(await screen.findByText("4")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(await screen.findByText("Petição inicial")).toBeInTheDocument();
    expect(await screen.findByText("Bruno Estagiário")).toBeInTheDocument();
  });

  it("período vazio mostra estado vazio explicativo, não gráfico zerado (regra 9)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/reports/agility`, () =>
        HttpResponse.json({
          on_time: 0,
          late: 0,
          pending: 0,
          avg_days_to_complete: null,
          avg_delay_days: null,
          staleness_hint: "Pode levar até 15 min para refletir mudanças recentes.",
        }),
      ),
      http.get(`${BASE_URL}/api/v1/reports/most-delayed`, () =>
        HttpResponse.json({ tasks: [], users: [] }),
      ),
    );

    renderPanel();

    expect(await screen.findByText("Sem dados no período")).toBeInTheDocument();
  });
});

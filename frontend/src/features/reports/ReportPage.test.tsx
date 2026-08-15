import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { ReportPage } from "@/features/reports/ReportPage";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

function renderPage(initialEntry: string): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <ReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ReportPage", () => {
  afterEach(() => server.resetHandlers());

  it("página genérica renderiza o relatório de produtividade (spec 072 §1/§8)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/reports/tabular/productivity`, () =>
        HttpResponse.json({
          items: [
            {
              post_id: "p1",
              responsible_name: "Ana Advogada",
              customer_name: "Cliente X",
              task_type_name: "Petição inicial",
              points: 8,
              scheduled_date: "2026-08-10",
              completed_at: "2026-08-11T10:00:00Z",
            },
          ],
          next_cursor: null,
          total: 1,
          points_total: 8,
          disabled_reason: null,
        }),
      ),
    );

    renderPage("/reports?report=productivity");

    expect(await screen.findByText("Ana Advogada")).toBeInTheDocument();
    expect(screen.getByText("Petição inicial")).toBeInTheDocument();
    expect(screen.getByText("Total de pontos:")).toBeInTheDocument();
  });

  it("página genérica renderiza o relatório de novos clientes, sem rodapé de pontos", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/reports/tabular/new_customers`, () =>
        HttpResponse.json({
          items: [
            {
              customer_id: "c1",
              name: "Maria Cliente",
              contact: "11999999999",
              city_state: "São Paulo/SP",
              origin_name: "Indicação",
              created_at: "2026-08-10T10:00:00Z",
            },
          ],
          next_cursor: null,
          total: 1,
          points_total: null,
          disabled_reason: null,
        }),
      ),
    );

    renderPage("/reports?report=new_customers");

    expect(await screen.findByText("Maria Cliente")).toBeInTheDocument();
    expect(screen.getByText("Indicação")).toBeInTheDocument();
    expect(screen.queryByText("Total de pontos:")).not.toBeInTheDocument();
  });

  it("relatório desligado mostra estado vazio explicativo (regra 5)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/reports/tabular/access_logs`, () =>
        HttpResponse.json({
          items: [],
          next_cursor: null,
          total: 0,
          points_total: null,
          disabled_reason: "Rastreamento de acesso desligado.",
        }),
      ),
    );

    renderPage("/reports?report=access_logs");

    expect(await screen.findByText("Rastreamento de acesso desligado.")).toBeInTheDocument();
  });
});

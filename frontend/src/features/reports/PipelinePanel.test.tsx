import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PipelinePanel } from "@/features/reports/PipelinePanel";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1", role: "ADMINISTRADOR" } }),
}));

const STALENESS_HINT = "Pode levar até 480 min para refletir mudanças recentes.";

function mockBiEndpoints(overrides: { idle_120?: number } = {}): void {
  server.use(
    http.get(`${BASE_URL}/api/v1/action-groups`, () =>
      HttpResponse.json({ items: [], next_cursor: null, total: 0 }),
    ),
    http.get(`${BASE_URL}/api/v1/bi/pipeline`, () =>
      HttpResponse.json({
        opportunities_month: 12,
        active: 30,
        archived: 4,
        idle_120: overrides.idle_120 ?? 0,
        closed_month: { value: 5, delta_pct: 25.0, previous: 4 },
        in_service: 8,
        closed_trend: [
          { month: "2026-03-01", closed: 2 },
          { month: "2026-04-01", closed: 3 },
          { month: "2026-05-01", closed: 0 },
          { month: "2026-06-01", closed: 1 },
          { month: "2026-07-01", closed: 4 },
          { month: "2026-08-01", closed: 5 },
        ],
        staleness_hint: STALENESS_HINT,
        crm_warning: "A qualidade destes indicadores depende do CRM alimentado.",
      }),
    ),
    http.get(`${BASE_URL}/api/v1/bi/pipeline/conversion`, () =>
      HttpResponse.json({
        period: "2026-08-01",
        groups: [
          {
            action_group_id: "g1",
            action_group_name: "Cível",
            opportunities: 10,
            closed: 5,
            conversion_rate: 50.0,
          },
          {
            action_group_id: "g2",
            action_group_name: "Trabalhista",
            opportunities: 0,
            closed: 0,
            conversion_rate: null,
          },
        ],
        staleness_hint: STALENESS_HINT,
      }),
    ),
    http.get(`${BASE_URL}/api/v1/bi/pipeline/portfolio`, () =>
      HttpResponse.json({
        group_by: "step",
        items: [{ step_id: 5, step_name: "Judicial", active: 30 }],
      }),
    ),
  );
}

function renderPanel(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/reports?tab=pipeline"]}>
        <PipelinePanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PipelinePanel (spec 074)", () => {
  afterEach(() => server.resetHandlers());

  it("mostra o indicador de defasagem da view e o aviso do CRM (regras 8 e 12)", async () => {
    mockBiEndpoints();
    renderPanel();

    expect(await screen.findByText(STALENESS_HINT)).toBeInTheDocument();
    expect(screen.getByText(/depende do CRM alimentado/)).toBeInTheDocument();
  });

  it("grupo sem oportunidades mostra taxa '—', nunca 0% (regras 10 e 11)", async () => {
    mockBiEndpoints();
    renderPanel();

    expect(await screen.findByText("Cível")).toBeInTheDocument();
    expect(screen.getByText("5/10 (50%)")).toBeInTheDocument();
    // Trabalhista aparece zerada (regra 10) com "—" na taxa (regra 11).
    expect(screen.getByText("Trabalhista")).toBeInTheDocument();
    expect(screen.getByText(/0\/0 \(—\)/)).toBeInTheDocument();
  });

  it("parados +120 dias disparam o alerta da aba (regra 4)", async () => {
    mockBiEndpoints({ idle_120: 3 });
    renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "3 processos parados há mais de 120 dias",
    );
  });
});

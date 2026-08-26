import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AskMetricsBox } from "@/features/reports/AskMetricsBox";
import { InsightCard } from "@/features/reports/InsightCard";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

function renderBox(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AskMetricsBox />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AskMetricsBox", () => {
  afterEach(() => server.resetHandlers());

  it("mostra o SQL antes de executar e só roda depois de confirmar (spec 089, regra 3)", async () => {
    const executions: unknown[] = [];
    server.use(
      http.post(`${BASE_URL}/api/v1/ai/analytics/ask`, async ({ request }) => {
        const body = (await request.json()) as { confirm_sql?: string };
        if (!body.confirm_sql) {
          return HttpResponse.json({
            sql: "SELECT month, lawsuits FROM ai_allowed_metrics LIMIT 1000",
            relations: ["ai_allowed_metrics"],
            touches_financial: false,
            executed: false,
            columns: [],
            rows: [],
            summary: null,
            query_id: null,
          });
        }
        executions.push(body.confirm_sql);
        return HttpResponse.json({
          sql: body.confirm_sql,
          relations: ["ai_allowed_metrics"],
          touches_financial: false,
          executed: true,
          columns: ["month", "lawsuits"],
          rows: [{ month: "2026-08-01", lawsuits: 12 }],
          summary: "1 linha(s)",
          query_id: "q-1",
        });
      }),
    );
    const user = userEvent.setup();
    renderBox();

    await user.type(
      screen.getByLabelText("Pergunte sobre os indicadores"),
      "quantos processos por mês?",
    );
    await user.click(screen.getByRole("button", { name: "Perguntar" }));

    // O SQL aparece — e nada foi executado ainda.
    expect(await screen.findByTestId("sql-text")).toHaveTextContent("ai_allowed_metrics");
    expect(executions).toHaveLength(0);
    expect(screen.queryByText("1 linha(s)")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Rodar consulta" }));

    expect(await screen.findByText("1 linha(s)")).toBeInTheDocument();
    expect(executions).toHaveLength(1);
  });

  it("cancelar tira a consulta da tela sem executar", async () => {
    server.use(
      http.post(`${BASE_URL}/api/v1/ai/analytics/ask`, () =>
        HttpResponse.json({
          sql: "SELECT month FROM ai_allowed_metrics LIMIT 1000",
          relations: ["ai_allowed_metrics"],
          touches_financial: false,
          executed: false,
          columns: [],
          rows: [],
          summary: null,
          query_id: null,
        }),
      ),
    );
    const user = userEvent.setup();
    renderBox();

    await user.type(screen.getByLabelText("Pergunte sobre os indicadores"), "quantos?");
    await user.click(screen.getByRole("button", { name: "Perguntar" }));
    await screen.findByTestId("sql-preview");
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByTestId("sql-preview")).not.toBeInTheDocument();
  });
});

describe("InsightCard", () => {
  it("todo aviso leva ao registro que o originou (regra 12)", () => {
    render(
      <MemoryRouter>
        <InsightCard
          insight={{
            id: "i-1",
            kind: "deadline_risk",
            severity: "critical",
            subject_type: "lawsuit",
            subject_id: "lawsuit-1",
            title: "Prazo vencendo",
            body: "2 tarefas com prazo em 2026-08-28.",
            suggested_action: null,
            dismissed_at: null,
            created_at: "2026-08-26T10:00:00Z",
          }}
          onDismiss={vi.fn()}
        />
      </MemoryRouter>,
    );

    const card = screen.getByTestId("insight-deadline_risk");
    expect(card).toHaveAttribute("data-severity", "critical");
    expect(screen.getByRole("link", { name: "Abrir o registro" })).toHaveAttribute(
      "href",
      "/lawsuits/lawsuit-1",
    );
  });
});

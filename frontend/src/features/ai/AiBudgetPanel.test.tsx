import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AiBudgetPanel } from "@/features/ai/AiBudgetPanel";
import type { BudgetData } from "@/features/ai/api";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

const BASE: BudgetData = {
  monthly_limit_usd: 100,
  spent_usd: 20,
  used_pct: 20,
  alert_pct: 80,
  is_blocking: true,
  is_alerting: false,
  is_exceeded: false,
  anomalies: [],
};

function withBudget(overrides: Partial<BudgetData> = {}, onSave?: (body: unknown) => void): void {
  server.use(
    http.get(`${BASE_URL}/api/v1/ai/budget`, () => HttpResponse.json({ ...BASE, ...overrides })),
    http.put(`${BASE_URL}/api/v1/ai/budget`, async ({ request }) => {
      onSave?.(await request.json());
      return HttpResponse.json({ ...BASE, ...overrides });
    }),
  );
}

function renderPanel(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <AiBudgetPanel />
    </QueryClientProvider>,
  );
}

describe("AiBudgetPanel", () => {
  afterEach(() => server.resetHandlers());

  it("mostra gasto, teto e quanto do mês já foi consumido (spec 090)", async () => {
    withBudget();
    renderPanel();

    expect(await screen.findByText("US$ 20.00")).toBeInTheDocument();
    expect(screen.getByText("US$ 100.00")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "20");
  });

  it("avisa ao passar do alerta sem dizer que bloqueou", async () => {
    withBudget({ spent_usd: 85, used_pct: 85, is_alerting: true });
    renderPanel();

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("passou de 80% do teto");
    expect(aviso).not.toHaveTextContent("bloquead");
  });

  it("com o teto estourado explica o que está acontecendo com as chamadas", async () => {
    withBudget({
      spent_usd: 120,
      used_pct: 120,
      is_alerting: true,
      is_exceeded: true,
    });
    renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent("chamadas de IA estão bloqueadas");
  });

  it("com bloqueio desligado, o texto muda: o gasto continua subindo", async () => {
    withBudget({
      spent_usd: 120,
      used_pct: 120,
      is_alerting: true,
      is_exceeded: true,
      is_blocking: false,
    });
    renderPanel();

    expect(await screen.findByRole("alert")).toHaveTextContent("gasto segue subindo");
  });

  it("mostra a feature que gastou muito acima da média dela", async () => {
    withBudget({
      anomalies: [{ feature_key: "copilot", today_usd: 9, daily_average_usd: 1, factor: 9 }],
    });
    renderPanel();

    expect(await screen.findByLabelText("Gasto fora do padrão")).toHaveTextContent(
      "copilot gastou hoje 9× a média diária dela",
    );
  });

  it("campo vazio salva como 'sem teto' — não como zero", async () => {
    const salvo = vi.fn();
    withBudget({}, salvo);
    const user = userEvent.setup();
    renderPanel();

    await user.clear(await screen.findByLabelText(/Teto mensal/));
    await user.click(screen.getByRole("button", { name: "Salvar orçamento" }));

    await waitFor(() =>
      expect(salvo).toHaveBeenCalledWith({
        monthly_limit_usd: null,
        alert_pct: 80,
        is_blocking: true,
      }),
    );
  });
});

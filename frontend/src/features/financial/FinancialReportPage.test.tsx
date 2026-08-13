import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { FinancialReportPage } from "@/features/financial/FinancialReportPage";

const getFinancialReport = vi.fn().mockResolvedValue({
  period_start: "2026-08-01",
  period_end: "2026-08-31",
  rows: [
    {
      dre_group_id: 1,
      dre_group_name: "Receitas",
      nature: "RECEITA",
      receita: 300,
      despesa: 0,
      total: 300,
    },
  ],
  total_receita: 300,
  total_despesa: 0,
  resultado: 300,
});
const listBankAccounts = vi.fn().mockResolvedValue({ items: [], next_cursor: null, total: 0 });

vi.mock("@/features/financial/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/financial/api")>(
    "@/features/financial/api",
  );
  return {
    ...actual,
    getFinancialReport: (...args: unknown[]) => getFinancialReport(...args),
    listBankAccounts: (...args: unknown[]) => listBankAccounts(...args),
  };
});

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/transactions?tab=reports"]}>
        <FinancialReportPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FinancialReportPage", () => {
  it("mostra as linhas por grupo DRE e o resultado (regra 5)", async () => {
    renderPage();

    await screen.findByText("Receitas");
    expect(screen.getAllByText("R$ 300,00").length).toBeGreaterThan(0);
    expect(getFinancialReport).toHaveBeenCalledWith("dre", expect.objectContaining({}));
  });

  it("troca para DFC ao clicar na aba (regra 2)", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Receitas");
    await user.click(screen.getByRole("tab", { name: "DFC" }));

    await waitFor(() => {
      expect(getFinancialReport).toHaveBeenLastCalledWith("dfc", expect.objectContaining({}));
    });
  });
});

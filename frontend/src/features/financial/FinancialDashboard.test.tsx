import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { FinancialDashboard } from "@/features/financial/FinancialDashboard";

const getTransactionStats = vi.fn().mockResolvedValue({
  balance: 100,
  balance_previous: 50,
  income_expected: 200,
  income_realized: 100,
  expense_expected: 80,
  expense_realized: 80,
  overdue: 30,
});
const getTransactionChart = vi.fn().mockResolvedValue([]);
const listBankAccountBalances = vi.fn().mockResolvedValue([]);

vi.mock("@/features/financial/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/financial/api")>(
    "@/features/financial/api",
  );
  return {
    ...actual,
    getTransactionStats: (...args: unknown[]) => getTransactionStats(...args),
    getTransactionChart: (...args: unknown[]) => getTransactionChart(...args),
    listBankAccountBalances: (...args: unknown[]) => listBankAccountBalances(...args),
  };
});

function renderDashboard(initialEntry = "/transactions"): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <FinancialDashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FinancialDashboard", () => {
  it("trocar regime refaz a consulta (regra 1, spec 059)", async () => {
    const user = userEvent.setup();
    renderDashboard();
    await waitFor(() =>
      expect(getTransactionStats).toHaveBeenCalledWith({
        regime: "due",
        month: expect.any(String),
      }),
    );

    await user.selectOptions(screen.getByLabelText("Regime de visualização"), "Data de pagamento");

    await waitFor(() =>
      expect(getTransactionStats).toHaveBeenCalledWith({
        regime: "payment",
        month: expect.any(String),
      }),
    );
  });

  it("navegação por mês preserva o regime escolhido (regra 8)", async () => {
    const user = userEvent.setup();
    renderDashboard();
    await waitFor(() => expect(getTransactionStats).toHaveBeenCalled());

    await user.selectOptions(screen.getByLabelText("Regime de visualização"), "Competência");
    await waitFor(() =>
      expect(getTransactionStats).toHaveBeenLastCalledWith(
        expect.objectContaining({ regime: "competence" }),
      ),
    );

    await user.click(screen.getByLabelText("Próximo mês"));

    await waitFor(() =>
      expect(getTransactionStats).toHaveBeenLastCalledWith(
        expect.objectContaining({ regime: "competence" }),
      ),
    );
  });

  it("saldo negativo aparece em vermelho, sem sinal duplicado (regra 10)", async () => {
    getTransactionStats.mockResolvedValueOnce({
      balance: -100,
      balance_previous: 50,
      income_expected: 0,
      income_realized: 0,
      expense_expected: 0,
      expense_realized: 0,
      overdue: 0,
    });
    renderDashboard();

    const balanceValue = await screen.findByText("-R$ 100,00");
    expect(balanceValue.textContent).not.toContain("-R$ -");
    expect(balanceValue.className).toContain("text-danger");
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { OverduePanel } from "@/features/financial/OverduePanel";

const getOverdueSummary = vi.fn().mockResolvedValue({
  total: 250,
  by_aging: [
    { bucket: "1-15", total: 100 },
    { bucket: "16-30", total: 50 },
    { bucket: "31-60", total: 0 },
    { bucket: "61-90", total: 0 },
    { bucket: "90+", total: 100 },
  ],
  top_debtors: [{ customer_id: "c1", customer_name: "Cliente Um", total: 250 }],
});
const listOverdue = vi.fn().mockResolvedValue({
  items: [
    {
      id: "t1",
      customer_id: "c1",
      customer_name: "Cliente Um",
      lawsuit_id: null,
      process_number: null,
      description: null,
      amount: 100,
      due_date: "2026-07-20",
      days_overdue: 10,
    },
  ],
  next_cursor: null,
  total: 1,
});
const listDunningRules = vi.fn().mockResolvedValue([]);

vi.mock("@/features/financial/dunning-api", async () => {
  const actual = await vi.importActual<typeof import("@/features/financial/dunning-api")>(
    "@/features/financial/dunning-api",
  );
  return {
    ...actual,
    getOverdueSummary: (...args: unknown[]) => getOverdueSummary(...args),
    listOverdue: (...args: unknown[]) => listOverdue(...args),
    listDunningRules: (...args: unknown[]) => listDunningRules(...args),
  };
});

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1", financialAccess: "FULL" } }),
}));

function renderPanel(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/transactions?tab=overdue"]}>
        <OverduePanel />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OverduePanel", () => {
  it("mostra o total atrasado e as faixas de aging (regra 2/11)", async () => {
    renderPanel();

    await screen.findByText("R$ 250,00");
    const chart = screen.getByRole("img", { name: "Atrasados por faixa" });
    expect(within(chart).getByText("1–15 dias")).toBeInTheDocument();
    expect(within(chart).getByText("90+ dias")).toBeInTheDocument();
    expect(await screen.findByText("Cliente Um")).toBeInTheDocument();
  });

  it("filtrar por faixa de aging refaz a consulta com o parâmetro certo", async () => {
    const user = userEvent.setup();
    renderPanel();
    await waitFor(() => expect(listOverdue).toHaveBeenCalledWith({ aging: undefined }));

    await user.selectOptions(screen.getByLabelText("Faixa de atraso"), "16-30");

    await waitFor(() => expect(listOverdue).toHaveBeenLastCalledWith({ aging: "16-30" }));
  });
});

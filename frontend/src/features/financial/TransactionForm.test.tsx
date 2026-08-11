import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { TransactionForm } from "@/features/financial/TransactionForm";
import {
  DEFAULT_TRANSACTION_FORM_VALUES,
  type TransactionFormValues,
} from "@/features/financial/schema";

const listFinancialCategories = vi.fn().mockResolvedValue({
  items: [{ id: "cat-1", name: "Categoria Teste" }],
  next_cursor: null,
  total: 1,
});

vi.mock("@/features/financial/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/financial/api")>(
    "@/features/financial/api",
  );
  return {
    ...actual,
    listFinancialCategories: (...args: unknown[]) => listFinancialCategories(...args),
  };
});

function Harness(): JSX.Element {
  const form = useForm<TransactionFormValues>({ defaultValues: DEFAULT_TRANSACTION_FORM_VALUES });
  return (
    <TransactionForm
      form={form}
      onSearchAccounts={() => Promise.resolve([])}
      onSearchCostCenters={() => Promise.resolve([])}
      onSearchCustomers={() => Promise.resolve([])}
      onSearchLawsuits={() => Promise.resolve([])}
    />
  );
}

describe("TransactionForm", () => {
  it("alterna os campos pelos 3 tipos (regra 2, spec 056)", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    // RECEITA (default): categoria + centro de custo aparecem, conta de destino não.
    expect(screen.getByText("Categoria")).toBeInTheDocument();
    expect(screen.getByLabelText("Centro de custo")).toBeInTheDocument();
    expect(screen.queryByLabelText("Conta de destino")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Tipo"), "TRANSFERENCIA");
    expect(screen.queryByText("Categoria")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Centro de custo")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Conta de destino")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Tipo"), "DESPESA");
    expect(screen.getByText("Categoria")).toBeInTheDocument();
    expect(screen.getByLabelText("Centro de custo")).toBeInTheDocument();
    expect(screen.queryByLabelText("Conta de destino")).not.toBeInTheDocument();
  });

  it("categoria filtra pelo tipo escolhido (regra 1, spec 056)", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByPlaceholderText("Buscar categoria…"), "Teste");
    await waitFor(() =>
      expect(listFinancialCategories).toHaveBeenCalledWith(
        expect.objectContaining({ type: "RECEITA" }),
      ),
    );

    await user.selectOptions(screen.getByLabelText("Tipo"), "DESPESA");
    listFinancialCategories.mockClear();
    await user.type(screen.getByPlaceholderText("Buscar categoria…"), "Teste");
    await waitFor(() =>
      expect(listFinancialCategories).toHaveBeenCalledWith(
        expect.objectContaining({ type: "DESPESA" }),
      ),
    );
  });
});

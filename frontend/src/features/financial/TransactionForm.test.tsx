import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
    listTransactionAttachments: vi.fn().mockResolvedValue([]),
  };
});

function Harness({ mode = "create" as const }: { mode?: "create" | "edit" } = {}): JSX.Element {
  const form = useForm<TransactionFormValues>({ defaultValues: DEFAULT_TRANSACTION_FORM_VALUES });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <TransactionForm
        form={form}
        mode={mode}
        transactionId={mode === "edit" ? "tx-1" : undefined}
        onSearchAccounts={() => Promise.resolve([])}
        onSearchCostCenters={() => Promise.resolve([])}
        onSearchCustomers={() => Promise.resolve([])}
        onSearchLawsuits={() => Promise.resolve([])}
      />
    </QueryClientProvider>
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

  it("modo parcelado mostra o preview das parcelas antes de salvar (regra 2/6, spec 057)", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Valor"), "10000"); // 100,00 em centavos
    await user.type(screen.getByLabelText("Vencimento"), "2026-01-31");
    await user.selectOptions(screen.getByLabelText("Modo"), "installment");
    await user.type(screen.getByLabelText("Número de parcelas"), "3");

    await waitFor(() => expect(screen.getByText(/1\/3/)).toBeInTheDocument());
    expect(screen.getByText(/2\/3/)).toBeInTheDocument();
    expect(screen.getByText(/3\/3/)).toBeInTheDocument();
    expect(screen.getByText(/31\/01\/2026/)).toBeInTheDocument();
    expect(screen.getByText(/28\/02\/2026/)).toBeInTheDocument();
    expect(screen.getByText(/31\/03\/2026/)).toBeInTheDocument();
  });

  it("marcar como interno mostra a explicação e a nota (regra 1/2, spec 058)", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.queryByLabelText("Nota interna (opcional)")).not.toBeInTheDocument();

    await user.click(screen.getByLabelText("Lançamento interno (só controle)"));
    expect(screen.getByText(/Não entra no saldo da conta/)).toBeInTheDocument();
    expect(screen.getByLabelText("Nota interna (opcional)")).toBeInTheDocument();
  });

  it("modo edição mostra a seção de anexos (spec 058, regra 6)", async () => {
    render(<Harness mode="edit" />);
    await waitFor(() => expect(screen.getByText("Anexos")).toBeInTheDocument());
    expect(screen.getByText("Anexar arquivo (máx. 50 MB)")).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LawsuitFinancialPanel } from "@/features/lawsuits/LawsuitFinancialPanel";
import type { FinancialSummary } from "@/features/lawsuits/api";

describe("LawsuitFinancialPanel", () => {
  it("renderiza zerado antes dos lançamentos (spec 056) e com '—' nos valores nulos", () => {
    const summary: FinancialSummary = {
      case_value: null,
      fees_value: null,
      received: 0,
      to_receive: 0,
      expenses: 0,
      net_result: 0,
    };
    render(<LawsuitFinancialPanel summary={summary} />);

    expect(screen.getByText("Valor da causa")).toBeInTheDocument();
    expect(screen.getByText("Honorários contratados")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(2);
    // Recebido / a receber / despesas / líquido: quatro cards zerados.
    expect(screen.getAllByText(/R\$.0,00/)).toHaveLength(4);
  });

  it("mostra os valores informados formatados em reais", () => {
    const summary: FinancialSummary = {
      case_value: 50000,
      fees_value: 10000,
      received: 0,
      to_receive: 0,
      expenses: 0,
      net_result: 0,
    };
    render(<LawsuitFinancialPanel summary={summary} />);

    expect(screen.getByText(/50\.000,00/)).toBeInTheDocument();
    expect(screen.getByText(/10\.000,00/)).toBeInTheDocument();
  });
});

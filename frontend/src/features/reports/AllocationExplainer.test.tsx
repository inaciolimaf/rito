import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AllocationExplainer } from "@/features/reports/AllocationExplainer";

const NOTE =
  "Custo alocado = custo direto (despesas lançadas no processo) + pontos das tarefas " +
  "concluídas × custo por ponto do mês (custo fixo do mês ÷ pontos concluídos no mês). " +
  "É uma aproximação de rateio, não contabilidade.";

describe("AllocationExplainer (spec 077)", () => {
  it("tooltip explica a fórmula do rateio (regra 11)", () => {
    render(<AllocationExplainer note={NOTE} />);

    const tooltip = screen.getByTestId("allocation-explainer");
    // O tooltip carrega a fórmula completa: custo direto + pontos × custo por ponto,
    // e o aviso de que é aproximação, não contabilidade.
    expect(tooltip).toHaveAttribute("title", NOTE);
    expect(tooltip.getAttribute("title")).toContain("custo direto");
    expect(tooltip.getAttribute("title")).toContain("custo por ponto do mês");
    expect(tooltip.getAttribute("title")).toContain("aproximação");
    expect(tooltip).toHaveAccessibleName("Como o custo alocado é calculado");
  });
});

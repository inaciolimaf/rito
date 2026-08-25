import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { BiTabPanel } from "@/features/reports/BiTabPanel";

function renderPanel(stalenessHint?: string | null): void {
  render(
    <MemoryRouter>
      <BiTabPanel
        filterFields={[{ key: "outcome", label: "Resultado", type: "text" }]}
        cards={<p>indicadores</p>}
        alert={<p>alerta</p>}
        stalenessHint={stalenessHint}
      >
        <p>conteúdo</p>
      </BiTabPanel>
    </MemoryRouter>,
  );
}

describe("BiTabPanel", () => {
  it("monta filtros, indicadores, alerta, conteúdo e defasagem na mesma ordem", () => {
    renderPanel("Pode levar até 8 h para refletir mudanças recentes.");

    expect(screen.getByLabelText("Resultado")).toBeInTheDocument();
    expect(screen.getByText("indicadores")).toBeInTheDocument();
    expect(screen.getByText("alerta")).toBeInTheDocument();
    expect(screen.getByText("conteúdo")).toBeInTheDocument();
    expect(screen.getByTestId("bi-refresh-indicator")).toHaveTextContent("8 h");
  });

  it("sem defasagem conhecida não inventa rodapé", () => {
    renderPanel(null);

    expect(screen.queryByTestId("bi-refresh-indicator")).not.toBeInTheDocument();
  });
});

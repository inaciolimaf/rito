import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RouteErrorBoundary } from "@/components/ErrorBoundary";

/** Quebra só na rota /crm: navegar para outra rota deve devolver a tela. */
function TelaQuebradaNaCrm(): JSX.Element {
  const { pathname } = useLocation();
  if (pathname === "/crm") throw new Error("falha de teste");
  return <p>Início</p>;
}

function Navegacao(): JSX.Element {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate("/home")}>
      Ir para o início
    </button>
  );
}

describe("RouteErrorBoundary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("mostra a mensagem de erro quando a tela quebra e se rearma ao navegar", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <MemoryRouter initialEntries={["/crm"]}>
        <Navegacao />
        <RouteErrorBoundary>
          <TelaQuebradaNaCrm />
        </RouteErrorBoundary>
      </MemoryRouter>,
    );
    expect(screen.getByText("Algo deu errado. Recarregue a página.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Ir para o início" }));
    expect(screen.getByText("Início")).toBeInTheDocument();
  });
});

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppLayout } from "@/components/shell/AppLayout";
import { NotFoundPage } from "@/components/shell/NotFoundPage";
import { ThemeProvider } from "@/providers/ThemeProvider";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({
    user: { name: "Usuária Teste", capabilities: [] },
    logout: vi.fn(),
  }),
}));

function renderApp(initialEntry: string): void {
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="/home" element={<div>Painel</div>} />
            <Route path="/customers" element={<div>Contatos</div>} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe("AppLayout", () => {
  afterEach(() => localStorage.clear());

  it("rota desconhecida mostra 404 dentro do layout, com link de volta", () => {
    renderApp("/rota-que-nao-existe");

    expect(screen.getByText("Página não encontrada.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Voltar para o início" })).toBeInTheDocument();
    // O shell (navegação principal) continua visível — o 404 é DENTRO do layout.
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
  });

  it("o drawer mobile fecha ao navegar", async () => {
    const user = userEvent.setup();
    renderApp("/home");

    await user.click(screen.getByRole("button", { name: "Abrir menu de navegação" }));
    const drawerLinks = screen.getAllByRole("link", { name: /contatos/i });
    expect(drawerLinks.length).toBeGreaterThan(1);

    await user.click(drawerLinks[drawerLinks.length - 1]!);

    expect(within(screen.getByRole("main")).getByText("Contatos")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /contatos/i })).toHaveLength(1);
  });
});

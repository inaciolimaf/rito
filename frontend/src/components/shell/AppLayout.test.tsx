import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
  // QueryClientProvider: o modal global de nova tarefa (spec 032) usa React Query.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
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
      </ThemeProvider>
    </QueryClientProvider>,
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

  it("rota que exige capability mostra 'sem permissão' com o menu ao lado (spec 138, regra 9)", () => {
    // O usuário do mock não tem `financial.read`. Chegar por link direto ao financeiro
    // mostrava, até aqui, erro genérico da API — nunca a explicação.
    renderApp("/transactions");

    expect(screen.getByRole("alert")).toHaveTextContent("Você não tem acesso a esta área.");
    // O shell continua: quem não pode ver esta tela precisa conseguir ir para outra.
    expect(screen.getByRole("navigation", { name: "Navegação principal" })).toBeInTheDocument();
  });
});

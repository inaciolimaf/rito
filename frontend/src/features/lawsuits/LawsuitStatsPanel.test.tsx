import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { getLawsuitStats, type LawsuitStats } from "@/features/lawsuits/api";
import { LawsuitStatsPanel } from "@/features/lawsuits/LawsuitStatsPanel";

vi.mock("@/features/lawsuits/api", () => ({
  getLawsuitStats: vi.fn(),
}));

const getStatsMock = vi.mocked(getLawsuitStats);

const STATS: LawsuitStats = {
  active: { value: 6, delta_pct: 100.0, previous: 3 },
  closed_this_month: { value: 2, delta_pct: 0.0, previous: 2 },
  archived_this_month: { value: 1, delta_pct: null, previous: 0 },
  volume_by_step: [
    { step: "Marketing", count: 5, pct: 83.3 },
    { step: "Negociação", count: 1, pct: 16.7 },
  ],
  closure_goal: null,
};

function UrlEcho(): JSX.Element {
  const [searchParams] = useSearchParams();
  return <output data-testid="view-param">{searchParams.get("view") ?? "(vazio)"}</output>;
}

function Harness(): JSX.Element {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LawsuitStatsPanel />
        <UrlEcho />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("LawsuitStatsPanel", () => {
  it("sem meta configurada mostra o convite (regra 6) e 'novo' na variação (regra 2)", async () => {
    getStatsMock.mockResolvedValue(STATS);
    render(<Harness />);

    expect(await screen.findByText("Nenhuma meta configurada para este mês.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Configurar meta" })).toHaveAttribute("href", "/goals");
    // Mês anterior zerado: "novo", nunca ∞ ou +100% inventado.
    expect(screen.getByText("novo este mês")).toBeInTheDocument();
    expect(screen.getByText("Volume por fase")).toBeInTheDocument();
  });

  it("clicar no card navega para a listagem com a visão filtrada (regra 8)", async () => {
    getStatsMock.mockResolvedValue(STATS);
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(await screen.findByRole("link", { name: /Fechamentos no mês/ }));
    expect(screen.getByTestId("view-param")).toHaveTextContent("closed_this_month");

    await user.click(screen.getByRole("link", { name: /Processos ativos/ }));
    expect(screen.getByTestId("view-param")).toHaveTextContent("active");

    await user.click(screen.getByRole("link", { name: /Arquivados no mês/ }));
    expect(screen.getByTestId("view-param")).toHaveTextContent("archived_this_month");
  });

  it("é recolhível", async () => {
    getStatsMock.mockResolvedValue(STATS);
    const user = userEvent.setup();
    render(<Harness />);

    const toggle = await screen.findByRole("button", { name: "Recolher painel" });
    await user.click(toggle);
    expect(screen.queryByText("Processos ativos")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mostrar painel" })).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { StatCard } from "@/components/domain/StatCard";

describe("StatCard", () => {
  it("mostra a variação em relação ao período anterior", () => {
    render(<StatCard label="Processos ativos" value={120} previousValue={100} />);

    expect(screen.getByText("Processos ativos")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText(/\+20%/)).toBeInTheDocument();
  });

  it("mostra o skeleton enquanto carrega", () => {
    const { container } = render(<StatCard label="Processos ativos" value={0} isLoading />);

    expect(screen.queryByText("Processos ativos")).not.toBeInTheDocument();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("vira link quando href é informado", () => {
    render(
      <MemoryRouter>
        <StatCard label="Processos ativos" value={10} href="/processos" />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link")).toHaveAttribute("href", "/processos");
  });
});

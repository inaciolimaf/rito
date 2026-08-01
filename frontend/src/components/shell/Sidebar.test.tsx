import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/components/shell/Sidebar";
import { NAV_ITEMS } from "@/components/shell/navItems";

const mockUseAuth = vi.fn();
vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderSidebar(initialEntry = "/home"): void {
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Sidebar onOpenPlaceholderModal={vi.fn()} />
    </MemoryRouter>,
  );
}

describe("Sidebar", () => {
  afterEach(() => {
    localStorage.clear();
    mockUseAuth.mockReset();
  });

  it("renderiza os 15 itens e marca o ativo pela rota", () => {
    mockUseAuth.mockReturnValue({
      user: { capabilities: ["financial.read", "settings.manage"] },
    });
    renderSidebar("/lawsuits");

    for (const item of NAV_ITEMS) {
      expect(screen.getByText(item.label)).toBeInTheDocument();
    }

    expect(screen.getByRole("link", { name: /processos/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("link", { name: /contatos/i })).not.toHaveAttribute("aria-current");
  });

  it("oculta item sem a capability exigida (não desabilita)", () => {
    mockUseAuth.mockReturnValue({ user: { capabilities: [] } });
    renderSidebar();

    expect(screen.queryByText("Financeiro")).not.toBeInTheDocument();
    expect(screen.queryByText("Configurações")).not.toBeInTheDocument();
    expect(screen.getByText("Meu Painel")).toBeInTheDocument();
  });

  it("persiste o estado de colapso", async () => {
    const user = userEvent.setup();
    mockUseAuth.mockReturnValue({ user: { capabilities: [] } });
    renderSidebar();

    await user.click(screen.getByRole("button", { name: "Recolher menu" }));
    expect(localStorage.getItem("rito.sidebar-collapsed")).toBe("true");
    expect(screen.getByRole("button", { name: "Expandir menu" })).toBeInTheDocument();
  });
});

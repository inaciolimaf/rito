import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { QuickAddMenu } from "@/components/shell/QuickAddMenu";

describe("QuickAddMenu", () => {
  it("mostra as 4 ações do dropdown Adicionar", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <QuickAddMenu onNewTask={vi.fn()} />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: /adicionar/i }));

    const menu = screen.getByRole("menu", { name: "Adicionar" });
    expect(menu).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Nova tarefa" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Novo contato" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Novo processo" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Nova receita/despesa" })).toBeInTheDocument();
  });

  it("Esc fecha o menu (spec 138, regra 10)", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <QuickAddMenu onNewTask={vi.fn()} />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: /adicionar/i }));
    expect(screen.getByRole("menu", { name: "Adicionar" })).toBeInTheDocument();

    // O menu anuncia `role="menu"`; fechar com Esc faz parte do padrão que ele anuncia.
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("menu", { name: "Adicionar" })).not.toBeInTheDocument();
  });
});

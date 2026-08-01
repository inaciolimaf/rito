import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { QuickAddMenu } from "@/components/shell/QuickAddMenu";

describe("QuickAddMenu", () => {
  it("mostra as 4 ações do dropdown Adicionar", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <QuickAddMenu />
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
});

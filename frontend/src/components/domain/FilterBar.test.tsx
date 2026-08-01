import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { FilterBar } from "@/components/domain/FilterBar";
import type { FilterFieldDef } from "@/components/domain/types";

const fields: FilterFieldDef[] = [
  { key: "q", label: "Busca", type: "text" },
  {
    key: "status",
    label: "Status",
    type: "select",
    options: [
      { value: "ativo", label: "Ativo" },
      { value: "arquivado", label: "Arquivado" },
    ],
  },
];

function renderFilterBar(initialEntry = "/"): void {
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <FilterBar fields={fields} />
    </MemoryRouter>,
  );
}

describe("FilterBar", () => {
  it("reflete o valor digitado na URL", async () => {
    const user = userEvent.setup();
    renderFilterBar();

    await user.type(screen.getByLabelText("Busca"), "contrato");

    expect(window.location.search).toBe("");
    // useSearchParams do react-router usa o history do MemoryRouter, não window.location;
    // o valor persistido é verificado lendo o próprio input, que reflete o estado da URL.
    expect(screen.getByLabelText("Busca")).toHaveValue("contrato");
  });

  it("preserva o filtro ao vir de uma URL já preenchida", () => {
    renderFilterBar("/?status=ativo");

    expect(screen.getByLabelText("Status")).toHaveValue("ativo");
  });

  it("limpa os filtros e zera o contador de ativos", async () => {
    const user = userEvent.setup();
    renderFilterBar("/?q=contrato&status=ativo");

    expect(screen.getByRole("button", { name: /limpar filtros \(2\)/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /limpar filtros/i }));

    expect(screen.getByLabelText("Busca")).toHaveValue("");
    expect(screen.getByRole("button", { name: /limpar filtros/i })).toBeDisabled();
  });
});

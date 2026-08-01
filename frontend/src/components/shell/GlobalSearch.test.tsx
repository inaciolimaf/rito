import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { GlobalSearch } from "@/components/shell/GlobalSearch";

function renderGlobalSearch(): void {
  render(
    <MemoryRouter>
      <input aria-label="Outro campo" />
      <GlobalSearch />
    </MemoryRouter>,
  );
}

describe("GlobalSearch", () => {
  it("'/' foca a busca quando o foco não está num campo de texto", async () => {
    const user = userEvent.setup();
    renderGlobalSearch();

    document.body.focus();
    await user.keyboard("/");

    expect(screen.getByRole("combobox")).toHaveFocus();
  });

  it("'/' não interfere quando o foco já está num campo de texto", async () => {
    const user = userEvent.setup();
    renderGlobalSearch();

    await user.click(screen.getByLabelText("Outro campo"));
    await user.keyboard("/");

    expect(screen.getByLabelText("Outro campo")).toHaveFocus();
    expect(screen.getByLabelText("Outro campo")).toHaveValue("/");
  });

  it("navega pelos resultados com as setas e abre com Enter", async () => {
    const user = userEvent.setup();
    renderGlobalSearch();

    const input = screen.getByRole("combobox");
    await user.click(input);
    await user.type(input, "ana");

    const option = await screen.findByRole("option", { name: "Ana Souza" });
    expect(option).toBeInTheDocument();

    await user.keyboard("{ArrowDown}");
    expect(option).toHaveAttribute("aria-selected", "true");

    await user.keyboard("{Enter}");
    expect(input).toHaveValue("");
  });
});

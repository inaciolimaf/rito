import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { QuickViewSelect } from "@/features/lawsuits/QuickViewSelect";

function UrlEcho(): JSX.Element {
  const [searchParams] = useSearchParams();
  return <output data-testid="view-param">{searchParams.get("view") ?? "(vazio)"}</output>;
}

function Harness(): JSX.Element {
  return (
    <MemoryRouter>
      <QuickViewSelect />
      <UrlEcho />
    </MemoryRouter>
  );
}

describe("QuickViewSelect", () => {
  it("trocar a visão atualiza a URL (regra 9)", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByLabelText("Visão")).toHaveValue("all");
    expect(screen.getByTestId("view-param")).toHaveTextContent("(vazio)");

    await user.selectOptions(screen.getByLabelText("Visão"), "idle_90d");
    expect(screen.getByTestId("view-param")).toHaveTextContent("idle_90d");

    // Voltar para "Todos" limpa o parâmetro — URL compartilhável sem ruído.
    await user.selectOptions(screen.getByLabelText("Visão"), "all");
    expect(screen.getByTestId("view-param")).toHaveTextContent("(vazio)");
  });
});

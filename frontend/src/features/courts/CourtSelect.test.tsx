import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CourtSelect } from "@/features/courts/CourtSelect";

vi.mock("@/features/courts/api", () => ({
  listCourts: vi.fn().mockResolvedValue([
    {
      id: 1,
      code: "TJSP",
      name: "Tribunal de Justiça de São Paulo",
      segment: "ESTADUAL",
      state_code: "SP",
      datajud_alias: "api_publica_tjsp",
      is_active: true,
    },
  ]),
}));

function Harness(): JSX.Element {
  return <CourtSelect value={[]} onChange={() => {}} />;
}

describe("CourtSelect", () => {
  it("busca por sigla e mostra o segmento como descrição", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.type(screen.getByLabelText("Tribunal"), "tjsp");

    const option = await screen.findByRole("option", { name: /TJSP/ });
    expect(option).toHaveTextContent("Tribunal de Justiça de São Paulo");
    expect(option).toHaveTextContent("Estadual");
  });
});

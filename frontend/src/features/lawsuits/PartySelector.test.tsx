import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import type { EntityOption } from "@/components/domain/types";
import { PartySelector, type PartyFormValue } from "@/features/lawsuits/PartySelector";

const ana: EntityOption = { id: "1", label: "Ana Cliente" };
const carlos: EntityOption = { id: "2", label: "Carlos Contrário" };

function Harness(): JSX.Element {
  const [value, setValue] = React.useState<PartyFormValue[]>([]);
  const onSearch = vi.fn().mockResolvedValue([ana, carlos]);
  return <PartySelector value={value} onChange={setValue} onSearch={onSearch} />;
}

async function pick(inputLabel: string, optionName: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(screen.getByRole("combobox", { name: inputLabel }), "a");
  const options = await screen.findAllByRole("option", { name: optionName });
  const option = options[0];
  if (!option) throw new Error(`Opção não encontrada: ${optionName}`);
  await user.click(option);
}

describe("PartySelector", () => {
  it("adiciona parte envolvida como ATIVO/cliente e contrária como CONTRARIA/não cliente", async () => {
    render(<Harness />);

    await pick("Adicionar partes envolvidas", "Ana Cliente");
    await pick("Partes contrárias", "Carlos Contrário");

    // Regra 7: ATIVO antes de CONTRARIA, independente da ordem de seleção.
    const chips = screen.getAllByRole("listitem");
    expect(chips[0]).toHaveTextContent("Ana Cliente");
    expect(chips[1]).toHaveTextContent("Carlos Contrário");
    expect(screen.getByLabelText("Polo de Ana Cliente")).toHaveValue("ATIVO");
    expect(screen.getByLabelText("Polo de Carlos Contrário")).toHaveValue("CONTRARIA");
  });

  it("remove uma parte pelo chip", async () => {
    render(<Harness />);

    await pick("Adicionar partes envolvidas", "Ana Cliente");
    expect(screen.getByText("Ana Cliente")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Remover Ana Cliente" }));

    await waitFor(() => expect(screen.queryByText("Ana Cliente")).not.toBeInTheDocument());
  });

  it("troca o polo pelo seletor do chip", async () => {
    render(<Harness />);

    await pick("Adicionar partes envolvidas", "Ana Cliente");

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText("Polo de Ana Cliente"), "PASSIVO");

    await waitFor(() =>
      expect(screen.getByLabelText("Polo de Ana Cliente")).toHaveValue("PASSIVO"),
    );
  });

  it("permite a mesma pessoa em polos distintos, mas não duas vezes no mesmo polo", async () => {
    render(<Harness />);

    await pick("Adicionar partes envolvidas", "Ana Cliente");
    await pick("Adicionar partes envolvidas", "Ana Cliente");
    expect(screen.getAllByText("Ana Cliente")).toHaveLength(1);

    await pick("Partes contrárias", "Ana Cliente");
    await waitFor(() => expect(screen.getAllByText("Ana Cliente")).toHaveLength(2));
  });
});

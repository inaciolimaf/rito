import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { getLawsuitFolders } from "@/features/lawsuits/api";
import { FolderAutocomplete } from "@/features/lawsuits/FolderAutocomplete";

vi.mock("@/features/lawsuits/api", () => ({
  getLawsuitFolders: vi.fn(),
}));

const getFoldersMock = vi.mocked(getLawsuitFolders);

/** Harness controlado — como o formulário usa o componente de verdade (o valor digitado
 * volta pela prop `value`). */
function Harness({ initial = "" }: { initial?: string }): JSX.Element {
  const [value, setValue] = React.useState(initial);
  return <FolderAutocomplete id="folder" value={value} onChange={setValue} />;
}

describe("FolderAutocomplete", () => {
  it("aceita valor novo — não é lista fechada (regra 1)", async () => {
    getFoldersMock.mockResolvedValue([{ name: "Ação Cível", count: 2 }]);
    const user = userEvent.setup();
    render(<Harness />);

    const input = screen.getByRole("combobox");
    await user.click(input);
    // Sugestões existentes aparecem (regra 7)…
    expect(await screen.findByRole("option", { name: /Ação Cível/ })).toBeInTheDocument();

    // …mas digitar um nome inexistente permanece no campo do mesmo jeito.
    await user.type(input, "Pasta Nova");
    expect(input).toHaveValue("Pasta Nova");
    await waitFor(() => expect(getFoldersMock).toHaveBeenCalled());
  });

  it("escolher uma sugestão preenche o campo com a grafia armazenada", async () => {
    getFoldersMock.mockResolvedValue([{ name: "Ação Cível", count: 2 }]);
    const user = userEvent.setup();
    render(<Harness initial="acao" />);

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: /Ação Cível/ }));
    expect(screen.getByRole("combobox")).toHaveValue("Ação Cível");
  });
});

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { EntityPicker } from "@/components/domain/EntityPicker";
import type { EntityOption } from "@/components/domain/types";

const anaOption: EntityOption = { id: "1", label: "Ana Souza" };
const brunoOption: EntityOption = { id: "2", label: "Bruno Lima" };
const options: EntityOption[] = [anaOption, brunoOption];

describe("EntityPicker", () => {
  it("faz busca com debounce e permite selecionar", async () => {
    const user = userEvent.setup();
    const onSearch = vi.fn().mockResolvedValue(options);
    const onChange = vi.fn();

    render(<EntityPicker value={[]} onChange={onChange} onSearch={onSearch} debounceMs={10} />);

    await user.type(screen.getByRole("combobox"), "ana");

    await waitFor(() => expect(onSearch).toHaveBeenCalledWith("ana"));
    const option = await screen.findByRole("option", { name: "Ana Souza" });
    await user.click(option);

    expect(onChange).toHaveBeenCalledWith([anaOption]);
  });

  it("permite remover um item já selecionado", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <EntityPicker
        value={[anaOption]}
        onChange={onChange}
        onSearch={vi.fn().mockResolvedValue([])}
        multiple
      />,
    );

    await user.click(screen.getByRole("button", { name: "Remover Ana Souza" }));

    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("resposta lenta de um prefixo antigo não sobrescreve a nova (spec 138, regra 6)", async () => {
    const user = userEvent.setup();
    // "sil" demora 300 ms; "silva" demora 10 ms — a lenta chega DEPOIS da certa.
    const onSearch = (query: string): Promise<EntityOption[]> =>
      new Promise((resolve) => {
        setTimeout(
          () => resolve([{ id: query, label: `resultado de ${query}` }]),
          query === "sil" ? 300 : 10,
        );
      });

    render(<EntityPicker value={[]} onChange={vi.fn()} onSearch={onSearch} debounceMs={20} />);

    const input = screen.getByRole("combobox");
    await user.type(input, "sil");
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 40));
    });
    await user.type(input, "va");

    await waitFor(() => expect(screen.getByText("resultado de silva")).toBeInTheDocument());
    // 400 ms depois, a resposta de "sil" já chegou — e foi descartada por ser velha.
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 400));
    });
    expect(screen.getByText("resultado de silva")).toBeInTheDocument();
    expect(screen.queryByText("resultado de sil")).not.toBeInTheDocument();
  }, 10000);

  it("busca sem resultado diz 'nenhum resultado' em vez de não abrir nada", async () => {
    const user = userEvent.setup();
    render(
      <EntityPicker
        value={[]}
        onChange={vi.fn()}
        onSearch={vi.fn().mockResolvedValue([])}
        debounceMs={10}
      />,
    );

    await user.type(screen.getByRole("combobox"), "zzz");

    expect(await screen.findByText("Nenhum resultado.")).toBeInTheDocument();
  });

  it("busca que falha mostra erro, e não vira unhandled rejection", async () => {
    const user = userEvent.setup();
    render(
      <EntityPicker
        value={[]}
        onChange={vi.fn()}
        onSearch={vi.fn().mockRejectedValue(new Error("500"))}
        debounceMs={10}
      />,
    );

    await user.type(screen.getByRole("combobox"), "ana");

    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível buscar.");
  });

  it("a opção ativa é anunciada por aria-activedescendant (spec 007 §9)", async () => {
    const user = userEvent.setup();
    render(
      <EntityPicker
        value={[]}
        onChange={vi.fn()}
        onSearch={vi.fn().mockResolvedValue(options)}
        debounceMs={10}
      />,
    );

    const input = screen.getByRole("combobox");
    await user.type(input, "a");
    await screen.findByRole("option", { name: "Ana Souza" });
    expect(input).not.toHaveAttribute("aria-activedescendant");

    await user.keyboard("{ArrowDown}");
    const activeId = input.getAttribute("aria-activedescendant");
    expect(activeId).toBeTruthy();
    expect(document.getElementById(activeId!)).toHaveTextContent("Ana Souza");
  });
});

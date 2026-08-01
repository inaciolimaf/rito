import { render, screen, waitFor } from "@testing-library/react";
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
});

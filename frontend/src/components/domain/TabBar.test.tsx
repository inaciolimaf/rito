import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TabBar } from "@/components/domain/TabBar";

const ITEMS = [
  { value: "a" as const, label: "Aba A" },
  { value: "b" as const, label: "Aba B" },
];

describe("TabBar", () => {
  it("marca a aba ativa e avisa a escolha de outra (refatoração 070)", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<TabBar items={ITEMS} active="a" ariaLabel="Teste" onSelect={onSelect} />);

    expect(screen.getByRole("tab", { name: "Aba A" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Aba B" })).toHaveAttribute("aria-selected", "false");

    await user.click(screen.getByRole("tab", { name: "Aba B" }));
    expect(onSelect).toHaveBeenCalledWith("b");
  });
});

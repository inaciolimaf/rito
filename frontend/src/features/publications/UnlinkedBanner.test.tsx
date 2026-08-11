import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { UnlinkedBanner } from "@/features/publications/UnlinkedBanner";

describe("UnlinkedBanner", () => {
  it("mostra o contador e dispara o filtro linked=false ao clicar (regras 1 e 2)", async () => {
    const onFilterUnlinked = vi.fn();
    const user = userEvent.setup();
    render(<UnlinkedBanner count={3} onFilterUnlinked={onFilterUnlinked} />);

    expect(screen.getByRole("status")).toHaveTextContent("3");
    expect(screen.getByRole("status")).toHaveTextContent("intimações não vinculadas");

    await user.click(screen.getByRole("button", { name: "Ver não vinculadas" }));
    expect(onFilterUnlinked).toHaveBeenCalledTimes(1);
  });

  it("some quando não há intimação não vinculada", () => {
    render(<UnlinkedBanner count={0} onFilterUnlinked={vi.fn()} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BulkActionBar } from "@/features/inbox/BulkActionBar";

const { mockBulkComplete } = vi.hoisted(() => ({ mockBulkComplete: vi.fn() }));

vi.mock("@/features/inbox/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/features/inbox/api")>();
  return { ...original, bulkComplete: mockBulkComplete };
});

describe("BulkActionBar", () => {
  beforeEach(() => {
    mockBulkComplete.mockReset();
    mockBulkComplete.mockResolvedValue(undefined);
  });

  it("não aparece sem seleção", () => {
    const { container } = render(
      <BulkActionBar selectedIds={[]} onClear={vi.fn()} onDone={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("aparece com seleção e Concluir dispara a ação em massa com os ids", async () => {
    const user = userEvent.setup();
    const onClear = vi.fn();
    const onDone = vi.fn();

    render(<BulkActionBar selectedIds={["p1", "p2"]} onClear={onClear} onDone={onDone} />);

    expect(screen.getByText("2 selecionada(s)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Concluir" }));

    expect(mockBulkComplete).toHaveBeenCalledWith(["p1", "p2"]);
    expect(onClear).toHaveBeenCalled();
    expect(onDone).toHaveBeenCalled();
  });
});

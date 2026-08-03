import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { InboxSettingsForm } from "@/features/inbox/InboxSettingsForm";
import type { InboxSectionKey } from "@/features/inbox/api";

const ORDER: InboxSectionKey[] = [
  "deadline",
  "publications",
  "unread",
  "urgent",
  "important",
  "others",
];

describe("InboxSettingsForm", () => {
  it("arrastar uma seção reordena a lista e salvar devolve a nova ordem", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn(async () => {});

    render(<InboxSettingsForm initialOrder={ORDER} onSave={onSave} />);

    const items = screen.getAllByRole("listitem");
    // Arrasta "Prazo fatal" (pos 0) para a posição de "Não lidas" (pos 2).
    fireEvent.dragStart(items[0]!);
    fireEvent.dragOver(items[2]!);
    fireEvent.drop(items[2]!);

    const labels = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(labels[0]).toContain("Intimações");
    expect(labels[1]).toContain("Não lidas");
    expect(labels[2]).toContain("Prazo fatal");

    await user.click(screen.getByRole("button", { name: "Salvar ordem" }));
    expect(onSave).toHaveBeenCalledWith([
      "publications",
      "unread",
      "deadline",
      "urgent",
      "important",
      "others",
    ]);
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";

describe("ConfirmDialog", () => {
  it("exige a confirmação digitada antes de habilitar o botão", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <ConfirmDialog
        open
        onOpenChange={() => undefined}
        title="Excluir processo"
        description="Esta ação não pode ser desfeita."
        destructive
        requireTypedConfirmation="EXCLUIR"
        onConfirm={onConfirm}
      />,
    );

    const confirmButton = screen.getByRole("button", { name: "Confirmar" });
    expect(confirmButton).toBeDisabled();

    await user.type(screen.getByLabelText(/digite/i), "EXCLUIR");
    expect(confirmButton).toBeEnabled();

    await user.click(confirmButton);
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("confirma direto quando não exige digitação", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();

    render(
      <ConfirmDialog
        open
        onOpenChange={() => undefined}
        title="Arquivar tarefa"
        onConfirm={onConfirm}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });
});

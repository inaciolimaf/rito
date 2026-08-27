import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { SecretRevealOnce } from "@/features/webhooks/SecretRevealOnce";

describe("SecretRevealOnce", () => {
  it("mostra o segredo e avisa que ele não volta (spec 093, regra 8)", () => {
    render(<SecretRevealOnce secret="whsec_abc123" onDismiss={vi.fn()} />);

    expect(screen.getByLabelText("Segredo do webhook")).toHaveTextContent("whsec_abc123");
    expect(screen.getByText(/não será mostrado de novo/)).toBeInTheDocument();
  });

  it("copiar leva o segredo para a área de transferência", async () => {
    // `userEvent.setup()` instala o próprio stub de clipboard, e o `navigator` do jsdom
    // só tem getter — então o espião entra por `spyOn` no que a biblioteca acabou de
    // montar, e não por atribuição.
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    render(<SecretRevealOnce secret="whsec_abc123" onDismiss={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Copiar" }));

    expect(writeText).toHaveBeenCalledWith("whsec_abc123");
    expect(screen.getByRole("button", { name: "Copiado" })).toBeInTheDocument();
  });

  it("fechar exige gesto explícito — o segredo não some sozinho", async () => {
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    render(<SecretRevealOnce secret="whsec_abc123" onDismiss={onDismiss} />);

    await user.click(screen.getByRole("button", { name: "Já guardei" }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});

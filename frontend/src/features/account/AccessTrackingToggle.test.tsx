import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AccessTrackingToggle } from "@/features/account/AccessTrackingToggle";

describe("AccessTrackingToggle", () => {
  it("desligado não mostra aviso de LGPD", () => {
    render(<AccessTrackingToggle enabled={false} onChange={vi.fn()} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("ligado mostra aviso de transparência com a equipe (spec 073 regra 2)", () => {
    render(<AccessTrackingToggle enabled={true} onChange={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Transparência com a equipe");
  });

  it("alternar chama onChange com o novo valor", async () => {
    const onChange = vi.fn();
    render(<AccessTrackingToggle enabled={false} onChange={onChange} />);

    await userEvent.click(screen.getByRole("checkbox"));

    expect(onChange).toHaveBeenCalledWith(true);
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StagnantBadge } from "@/components/domain/StagnantBadge";

describe("StagnantBadge", () => {
  it("mostra os dias parado", () => {
    render(<StagnantBadge daysInStage={8} stagnantDays={5} />);
    expect(screen.getByTestId("stagnant-badge")).toHaveTextContent("Estagnado há 8 dias");
  });

  it("tooltip explica a regra da etapa", () => {
    render(<StagnantBadge daysInStage={8} stagnantDays={5} />);
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "Esta etapa marca como estagnado após 5 dias sem mudar de etapa.",
    );
  });
});

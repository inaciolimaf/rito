import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { formatStaleness, StalenessIndicator } from "@/features/integrations/StalenessIndicator";

describe("StalenessIndicator (spec 078, §6)", () => {
  it("mostra relógio com tooltip 'atualizado há X' (regra: defasagem visível)", () => {
    const computedAt = new Date(Date.now() - 45 * 60 * 1000).toISOString();
    render(<StalenessIndicator computedAt={computedAt} isStale={false} />);

    const indicator = screen.getByTestId("staleness-indicator");
    expect(indicator).toHaveTextContent("atualizado há 45 min");
    expect(indicator).toHaveAttribute("title", expect.stringContaining("atualizado há 45 min"));
    expect(indicator).not.toHaveTextContent("desatualizado");
  });

  it("marca como desatualizado quando a defasagem passa de 2× o intervalo (regra 6)", () => {
    const computedAt = new Date(Date.now() - 17 * 3600 * 1000).toISOString();
    render(<StalenessIndicator computedAt={computedAt} isStale={true} />);

    const indicator = screen.getByTestId("staleness-indicator");
    expect(indicator).toHaveTextContent("atualizado há 17 h (desatualizado)");
  });

  it("agregado nunca atualizado informa 'nunca atualizado'", () => {
    render(<StalenessIndicator computedAt={null} isStale={true} />);

    const indicator = screen.getByTestId("staleness-indicator");
    expect(indicator).toHaveTextContent("nunca atualizado");
    expect(indicator).toHaveAttribute(
      "title",
      "Este agregado ainda não foi atualizado pelo orquestrador.",
    );
  });

  it("formatStaleness cobre as faixas de grandeza", () => {
    const now = new Date("2026-08-25T12:00:00Z");
    expect(formatStaleness("2026-08-25T11:59:40Z", now)).toBe("atualizado há menos de 1 min");
    expect(formatStaleness("2026-08-25T11:30:00Z", now)).toBe("atualizado há 30 min");
    expect(formatStaleness("2026-08-25T04:00:00Z", now)).toBe("atualizado há 8 h");
    expect(formatStaleness("2026-08-22T12:00:00Z", now)).toBe("atualizado há 3 d");
    expect(formatStaleness(null, now)).toBe("nunca atualizado");
  });
});

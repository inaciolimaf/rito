import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TermStatus } from "@/features/monitored-terms/api";
import { TermStatusBadge } from "@/features/monitored-terms/TermStatusBadge";

describe("TermStatusBadge", () => {
  it.each<[TermStatus, string]>([
    ["PENDENTE", "Pendente"],
    ["SINCRONIZANDO", "Sincronizando"],
    ["ATIVO", "Ativo"],
    ["FALHA", "Falha"],
    ["PAUSADO", "Pausado"],
  ])("reflete o status %s como %s", (status, label) => {
    render(<TermStatusBadge status={status} />);
    expect(screen.getByTestId("term-status-badge")).toHaveTextContent(label);
  });
});

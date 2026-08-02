import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PartiesCell } from "@/features/lawsuits/LawsuitListCells";

describe("PartiesCell", () => {
  it("mostra as 2 primeiras partes + contador (regra 12)", () => {
    render(
      <PartiesCell
        parties={[
          { name: "Ana", pole: "ATIVO" },
          { name: "Bruno", pole: "PASSIVO" },
          { name: "Carlos", pole: "CONTRARIA" },
          { name: "Diana", pole: "CONTRARIA" },
        ]}
        partiesTotal={4}
      />,
    );
    expect(screen.getByText(/Ana, Bruno/)).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.queryByText(/Carlos/)).not.toBeInTheDocument();
  });

  it("sem contador quando cabem 2 ou menos", () => {
    render(<PartiesCell parties={[{ name: "Ana", pole: "ATIVO" }]} partiesTotal={1} />);
    expect(screen.getByText("Ana")).toBeInTheDocument();
    expect(screen.queryByText(/\+\d/)).not.toBeInTheDocument();
  });
});

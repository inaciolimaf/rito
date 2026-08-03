import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RecurrencePreview } from "@/features/posts/RecurrencePreview";

describe("RecurrencePreview", () => {
  it("mostra as 5 próximas datas da série semanal (DD/MM/AAAA)", () => {
    render(<RecurrencePreview scheduledDate="2026-08-10" period="SEMANAL" repeatOn="DIA_EXATO" />);

    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items).toEqual(["17/08/2026", "24/08/2026", "31/08/2026", "07/09/2026", "14/09/2026"]);
  });

  it("série mensal no dia 31 clampa em fevereiro e volta ao 31 em março (regra 3)", () => {
    render(<RecurrencePreview scheduledDate="2026-01-31" period="MENSAL" repeatOn="DIA_EXATO" />);

    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items.slice(0, 3)).toEqual(["28/02/2026", "31/03/2026", "30/04/2026"]);
  });

  it("respeita o limite de ocorrências (regra 6: o template já conta)", () => {
    render(
      <RecurrencePreview
        scheduledDate="2026-08-10"
        period="SEMANAL"
        repeatOn="DIA_EXATO"
        maxOccurrences={3}
      />,
    );

    // max=3 contando a 1ª (o template) → só 2 datas futuras aparecem.
    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items).toEqual(["17/08/2026", "24/08/2026"]);
  });

  it("sem data do compromisso não renderiza nada", () => {
    const { container } = render(
      <RecurrencePreview scheduledDate="" period="SEMANAL" repeatOn="DIA_EXATO" />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

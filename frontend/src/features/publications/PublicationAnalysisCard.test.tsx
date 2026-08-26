import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PublicationAnalysisCard } from "@/features/publications/PublicationAnalysisCard";
import type { PublicationAnalysisData } from "@/features/publications/analysis";

function makeAnalysis(overrides: Partial<PublicationAnalysisData> = {}): PublicationAnalysisData {
  return {
    id: "analysis-1",
    publication_id: "pub-1",
    summary: "Intimação para apresentar contestação.",
    act_type: "intimacao_prazo",
    requires_action: true,
    deadline_days: 15,
    deadline_kind: "uteis",
    deadline_date: "2026-08-26",
    deadline_confidence: 0.93,
    should_prefill_deadline: true,
    suggested_task_type_id: "type-1",
    suggested_user_id: "user-1",
    reasoning: "O texto diz 'prazo de 15 dias úteis para contestar'.",
    model: "fabricante-x/modelo-y",
    reviewed_by: null,
    reviewed_at: null,
    human_correction: null,
    created_at: "2026-08-05T10:00:00Z",
    ...overrides,
  };
}

describe("PublicationAnalysisCard", () => {
  it("mostra confiança e o raciocínio ao lado do prazo (spec 086, regras 4 e 7)", () => {
    render(
      <PublicationAnalysisCard analysis={makeAnalysis()} onAnalyze={vi.fn()} onReview={vi.fn()} />,
    );

    expect(screen.getByTestId("confidence-badge")).toHaveAttribute("data-level", "high");
    expect(screen.getByTestId("confidence-badge")).toHaveTextContent("93%");
    expect(screen.getByTestId("deadline-reasoning")).toHaveTextContent("15 dias úteis");
    // Regra 1: o rótulo deixa explícito que ainda é sugestão.
    expect(screen.getByLabelText(/Prazo sugerido pela IA/)).toHaveValue("2026-08-26");
  });

  it("confiança baixa não preenche o campo e avisa (regra 4)", () => {
    render(
      <PublicationAnalysisCard
        analysis={makeAnalysis({ deadline_confidence: 0.4, should_prefill_deadline: false })}
        onAnalyze={vi.fn()}
        onReview={vi.fn()}
      />,
    );

    expect(screen.getByTestId("confidence-badge")).toHaveAttribute("data-level", "low");
    expect(screen.getByLabelText(/Prazo sugerido pela IA/)).toHaveValue("");
    expect(screen.getByRole("alert")).toHaveTextContent("confiança está baixa");
  });

  it("confirmar manda a data que está no campo, não a da IA (regra 1)", async () => {
    const onReview = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <PublicationAnalysisCard analysis={makeAnalysis()} onAnalyze={vi.fn()} onReview={onReview} />,
    );

    const campo = screen.getByLabelText(/Prazo sugerido pela IA/);
    await user.clear(campo);
    await user.type(campo, "2026-08-20");
    await user.click(screen.getByRole("button", { name: /Confirmar prazo/ }));

    expect(onReview).toHaveBeenCalledWith({ approved: true, deadline_date: "2026-08-20" });
  });

  it("sem prazo identificado, não oferece campo de data (regra 5)", () => {
    render(
      <PublicationAnalysisCard
        analysis={makeAnalysis({
          requires_action: false,
          deadline_date: null,
          deadline_days: null,
          should_prefill_deadline: false,
        })}
        onAnalyze={vi.fn()}
        onReview={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("deadline-review")).not.toBeInTheDocument();
    expect(screen.getByText(/não identificou prazo/)).toBeInTheDocument();
  });
});

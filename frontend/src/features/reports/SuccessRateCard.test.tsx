import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SuccessRateCard } from "@/features/reports/SuccessRateCard";
import type { SuccessRateGroupData, SuccessTrendPointData } from "@/features/reports/api";

const RATE_NOTE =
  "Taxa de sucesso = ganhos ÷ (ganhos + perdidos + acordos), calculada só sobre " +
  "processos concluídos. Acordos entram no denominador, mas não no numerador.";

function makeGroup(overrides: Partial<SuccessRateGroupData> = {}): SuccessRateGroupData {
  return {
    action_group_id: "g1",
    action_group_name: "Cível",
    won: 6,
    lost: 3,
    settled: 1,
    concluded: 10,
    success_rate: 60.0,
    small_sample: false,
    ...overrides,
  };
}

function makeTrend(): SuccessTrendPointData[] {
  // Regra 6: 24 meses; meses sem concluído têm taxa null.
  return Array.from({ length: 24 }, (_, index) => ({
    month: `2024-${String((index % 12) + 1).padStart(2, "0")}-01`,
    won: index % 2,
    lost: 0,
    settled: 0,
    concluded: index % 2,
    success_rate: index % 2 === 0 ? null : 100,
  }));
}

describe("SuccessRateCard (spec 075)", () => {
  it("tooltip explica o critério da taxa (regra 2)", () => {
    render(<SuccessRateCard group={makeGroup()} trend={makeTrend()} rateNote={RATE_NOTE} />);

    const tooltip = screen.getByTestId("success-rate-tooltip");
    // O critério é decisão de negócio: acordo no denominador, fora do numerador.
    expect(tooltip).toHaveAttribute("title", RATE_NOTE);
    expect(tooltip.getAttribute("title")).toContain("Acordos entram no denominador");
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("zero concluídos exibe '—', nunca 0% (regra 11)", () => {
    render(
      <SuccessRateCard
        group={makeGroup({ won: 0, lost: 0, settled: 0, concluded: 0, success_rate: null })}
        trend={makeTrend()}
        rateNote={RATE_NOTE}
      />,
    );

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("menos de 10 concluídos mostra aviso de amostra (regra 5) e sparkline de 24 meses (regra 6)", () => {
    render(
      <SuccessRateCard
        group={makeGroup({ concluded: 2, small_sample: true })}
        trend={makeTrend()}
        rateNote={RATE_NOTE}
      />,
    );

    expect(screen.getByRole("note")).toHaveTextContent(/Amostra pequena/);
    const sparkline = screen.getByTestId("success-sparkline");
    // Só os 12 meses com taxa viram barra; os 12 null são lacuna, nunca zero.
    expect(sparkline.querySelectorAll("rect")).toHaveLength(12);
  });
});

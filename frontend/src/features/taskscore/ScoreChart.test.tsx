import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ScoreChartResponse } from "@/features/taskscore/api";
import { ScoreChart } from "@/features/taskscore/ScoreChart";

const MONTHLY: ScoreChartResponse = {
  granularity: "monthly",
  current: 12,
  previous: 8,
  goal: 50,
  days: [],
};

describe("ScoreChart", () => {
  it("compara mês atual × mês anterior × meta (spec 039 §8 frontend)", () => {
    render(<ScoreChart chart={MONTHLY} />);

    expect(screen.getByText("Mês atual × mês anterior × meta")).toBeInTheDocument();
    expect(screen.getByText("Mês anterior")).toBeInTheDocument();
    expect(screen.getByText("Mês atual")).toBeInTheDocument();
    expect(screen.getByText("Meta")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("50")).toBeInTheDocument();
  });

  it("sem meta o gráfico omite a terceira barra (regra 3)", () => {
    render(<ScoreChart chart={{ ...MONTHLY, goal: null }} />);

    expect(screen.queryByText("Meta")).not.toBeInTheDocument();
  });

  it("visão diária mostra os pontos por dia", () => {
    render(
      <ScoreChart
        chart={{
          granularity: "daily",
          current: 0,
          previous: 0,
          goal: null,
          days: [{ label: "05/08", value: 12 }],
        }}
      />,
    );

    expect(screen.getByText("Pontos por dia no mês")).toBeInTheDocument();
    expect(screen.getByText("05/08")).toBeInTheDocument();
  });
});

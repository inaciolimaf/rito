import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CYCLE_SERIES, CycleBarChart } from "@/features/reports/CycleBarChart";
import type { TimeFeesGroupData } from "@/features/reports/api";

function makeGroup(overrides: Partial<TimeFeesGroupData> = {}): TimeFeesGroupData {
  return {
    action_group_id: "g1",
    action_group_name: "Cível",
    lawsuits: 3,
    cycles: {
      prospecting_days: 30,
      production_days: 120,
      execution_days: 90,
      full_cycle_days: 240,
    },
    ...overrides,
  };
}

describe("CycleBarChart (spec 076)", () => {
  it("gráfico por grupo mostra os 4 ciclos lado a lado, nas 4 cores da spec (regra 10 e §6)", () => {
    render(
      <CycleBarChart
        groups={[
          makeGroup(),
          makeGroup({
            action_group_id: "g2",
            action_group_name: "Trabalhista",
            cycles: {
              prospecting_days: 10,
              production_days: 60,
              execution_days: 45,
              full_cycle_days: 115,
            },
          }),
        ]}
      />,
    );

    const chart = screen.getByTestId("cycle-bar-chart");
    // 2 grupos × 4 ciclos = 8 barras.
    const bars = chart.querySelectorAll("rect");
    expect(bars).toHaveLength(8);
    // As 4 cores fixas da spec §6: verde, azul claro, azul escuro, vermelho.
    expect(CYCLE_SERIES.map((series) => series.color)).toEqual([
      "#16a34a",
      "#38bdf8",
      "#1e3a8a",
      "#dc2626",
    ]);
    for (const series of CYCLE_SERIES) {
      const colored = chart.querySelectorAll(`rect[fill="${series.color}"]`);
      expect(colored.length).toBe(2);
      // A legenda associa cada cor ao nome do ciclo.
      expect(screen.getByText(series.label)).toBeInTheDocument();
    }
  });

  it("ciclo nulo vira lacuna, nunca barra de altura zero (regra 2)", () => {
    render(
      <CycleBarChart
        groups={[
          makeGroup({
            cycles: {
              prospecting_days: 30,
              production_days: null,
              execution_days: null,
              full_cycle_days: null,
            },
          }),
        ]}
      />,
    );

    const chart = screen.getByTestId("cycle-bar-chart");
    // Só a prospecção tem barra; os 3 ciclos sem data são lacuna.
    expect(chart.querySelectorAll("rect")).toHaveLength(1);
    expect(chart.querySelectorAll('rect[fill="#16a34a"]')).toHaveLength(1);
  });

  it("sem grupos mostra mensagem vazia", () => {
    render(<CycleBarChart groups={[]} />);
    expect(screen.getByText("Nenhum processo fechado ainda.")).toBeInTheDocument();
  });
});

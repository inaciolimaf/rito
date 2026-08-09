import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ScoreSummary } from "@/features/taskscore/api";
import { UserScoreCard } from "@/features/taskscore/UserScoreCard";

const BASE: ScoreSummary = {
  user_id: "u1",
  user_name: "Ana Advogada",
  points: 80,
  tasks_completed: 10,
  on_time: 9,
  late: 1,
  assigned: 12,
  engagement: 0.833,
  points_goal: 100,
  goal_pct: 80.0,
};

describe("UserScoreCard", () => {
  it("mostra o progresso da meta com barra (spec 039 §8 frontend)", () => {
    render(<UserScoreCard summary={BASE} />);

    expect(screen.getByText("Ana Advogada")).toBeInTheDocument();
    expect(screen.getByText("80")).toBeInTheDocument();
    expect(screen.getByText("80% da meta (100 pts)")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Alcance da meta de pontos" })).toHaveAttribute(
      "aria-valuenow",
      "80",
    );
    expect(screen.getByText(/10 concluídas · 9 no prazo · 1 em atraso/)).toBeInTheDocument();
  });

  it("sem meta mostra '—', nunca 0% (regra 3)", () => {
    render(<UserScoreCard summary={{ ...BASE, points_goal: null, goal_pct: null }} />);

    expect(screen.getByText("Meta: —")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });
});

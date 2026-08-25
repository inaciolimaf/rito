import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentStepsTimeline } from "@/features/ai/AgentStepsTimeline";
import type { StepData } from "@/features/ai/threads";

function makeStep(overrides: Partial<StepData> = {}): StepData {
  return {
    id: `step-${overrides.step ?? 1}`,
    step: 1,
    node: "think",
    kind: "node",
    input: null,
    output: { messages: [] },
    duration_ms: 42,
    error: null,
    created_at: "2026-08-26T10:00:00Z",
    ...overrides,
  };
}

describe("AgentStepsTimeline", () => {
  it("lista o que o agente fez, na ordem, com nó e duração (spec 082, regra 7)", () => {
    render(
      <AgentStepsTimeline
        steps={[
          makeStep(),
          makeStep({ step: 2, node: "propose", kind: "interrupt", output: { pending: true } }),
        ]}
      />,
    );

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("1. Passo");
    expect(items[0]).toHaveTextContent("think");
    expect(items[0]).toHaveTextContent("42 ms");
    expect(items[1]).toHaveTextContent("2. Pediu confirmação");
  });

  it("passo que falhou aparece com o erro, não some da linha do tempo", () => {
    render(
      <AgentStepsTimeline
        steps={[makeStep({ kind: "error", error: "nó excedeu 300s", output: null })]}
      />,
    );

    expect(screen.getByText("nó excedeu 300s")).toBeInTheDocument();
  });

  it("passo truncado explica que só a referência ficou (regra 8)", () => {
    render(
      <AgentStepsTimeline
        steps={[makeStep({ output: { truncated: true, size_bytes: 204800, keys: ["output"] } })]}
      />,
    );

    expect(screen.getByText(/200 KB/)).toBeInTheDocument();
  });

  it("sem passos, explica que ainda não houve nenhum", () => {
    render(<AgentStepsTimeline steps={[]} />);

    expect(screen.getByText("Nenhum passo ainda")).toBeInTheDocument();
  });
});

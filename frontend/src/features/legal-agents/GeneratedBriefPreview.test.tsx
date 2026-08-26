import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GeneratedBriefPreview } from "@/features/legal-agents/GeneratedBriefPreview";
import { GenerationProgress } from "@/features/legal-agents/GenerationProgress";
import type { AgentGenerationData } from "@/features/legal-agents/api";

function makeGeneration(overrides: Partial<AgentGenerationData> = {}): AgentGenerationData {
  return {
    id: "gen-1",
    agent_id: "agent-1",
    lawsuit_id: "lawsuit-1",
    thread_id: null,
    user_instructions: null,
    content: { format: "html", html: "<h1>RECLAMAÇÃO TRABALHISTA</h1><p>Dos fatos.</p>" },
    template_used_id: null,
    model: "fabricante-x/modelo-y",
    tokens_used: 2000,
    warnings: [],
    saved_template_id: null,
    tool_labels: ["abrindo o processo"],
    created_at: "2026-08-26T10:00:00Z",
    ...overrides,
  };
}

describe("GeneratedBriefPreview", () => {
  it("marca a peça como minuta, de forma inequívoca (spec 087, regra 4)", () => {
    render(<GeneratedBriefPreview generation={makeGeneration()} onOpenInEditor={vi.fn()} />);

    const aviso = screen.getByTestId("draft-warning");
    expect(aviso).toHaveTextContent("Minuta gerada por IA");
    expect(aviso).toHaveTextContent("não é documento do processo até você salvar");
    // Regra 12: o botão diz que salvar é uma decisão, não um efeito colateral.
    expect(screen.getByRole("button", { name: /Salvar e abrir no editor/ })).toBeInTheDocument();
  });

  it("mostra as citações que o guarda-corpo removeu (regra 6)", () => {
    render(
      <GeneratedBriefPreview
        generation={makeGeneration({
          warnings: [{ kind: "súmula", text: "Súmula 331 do TST" }],
        })}
        onOpenInEditor={vi.fn()}
      />,
    );

    expect(screen.getByTestId("citation-warnings")).toHaveTextContent("Súmula 331 do TST");
  });

  it("sem citação removida, não inventa alerta", () => {
    render(<GeneratedBriefPreview generation={makeGeneration()} onOpenInEditor={vi.fn()} />);

    expect(screen.queryByTestId("citation-warnings")).not.toBeInTheDocument();
  });
});

describe("GenerationProgress", () => {
  it("mostra qual ferramenta o agente está usando, em português (regra 8)", () => {
    render(
      <GenerationProgress
        toolLabels={["abrindo o processo", "lendo o andamento do processo"]}
        isGenerating
      />,
    );

    const progresso = screen.getByTestId("generation-progress");
    expect(progresso).toHaveTextContent("Escrevendo a minuta…");
    expect(progresso).toHaveTextContent("abrindo o processo");
    expect(progresso).toHaveTextContent("lendo o andamento do processo");
  });

  it("quando termina, para de dizer que está escrevendo", () => {
    render(<GenerationProgress toolLabels={["abrindo o processo"]} isGenerating={false} />);

    expect(screen.getByTestId("generation-progress")).toHaveTextContent("Minuta pronta.");
  });
});

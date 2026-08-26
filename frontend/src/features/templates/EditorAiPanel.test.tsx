import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AiSuggestionOverlay } from "@/features/templates/AiSuggestionOverlay";
import { ReviewChecklistPanel } from "@/features/templates/ReviewChecklistPanel";
import { SelectionToolbar } from "@/features/templates/SelectionToolbar";
import { SlashCommandMenu } from "@/features/templates/SlashCommandMenu";

describe("SlashCommandMenu", () => {
  it("lista os comandos de IA quando aberto (spec 088 §6)", () => {
    render(<SlashCommandMenu open aiAvailable onPick={vi.fn()} onClose={vi.fn()} />);

    const menu = screen.getByTestId("slash-menu");
    expect(menu).toHaveTextContent("Continuar escrevendo");
    expect(menu).toHaveTextContent("Revisar a peça");
    expect(menu).toHaveTextContent("Não inventa citação");
  });

  it("sem IA configurada, nenhum comando de IA aparece (regra 11)", () => {
    render(<SlashCommandMenu open aiAvailable={false} onPick={vi.fn()} onClose={vi.fn()} />);

    expect(screen.getByTestId("slash-menu")).toHaveTextContent("não tem IA configurada");
    expect(screen.queryByText("Continuar escrevendo")).not.toBeInTheDocument();
  });
});

describe("AiSuggestionOverlay", () => {
  it("Tab aceita e Esc descarta a sugestão (regra 2)", async () => {
    const onAccept = vi.fn();
    const onDiscard = vi.fn();
    const user = userEvent.setup();
    render(
      <AiSuggestionOverlay
        suggestion="Diante do exposto, requer a procedência."
        isStreaming={false}
        onAccept={onAccept}
        onDiscard={onDiscard}
      />,
    );

    expect(screen.getByTestId("ai-suggestion")).toHaveTextContent("requer a procedência");

    await user.keyboard("{Tab}");
    expect(onAccept).toHaveBeenCalledOnce();

    await user.keyboard("{Escape}");
    expect(onDiscard).toHaveBeenCalledOnce();
  });
});

describe("SelectionToolbar", () => {
  it("aparece com texto selecionado e some sem seleção", () => {
    const { rerender } = render(
      <SelectionToolbar
        selectionLength={42}
        aiAvailable
        onRewrite={vi.fn()}
        onTone={vi.fn()}
        onGround={vi.fn()}
      />,
    );

    expect(screen.getByTestId("selection-toolbar")).toHaveTextContent("42 caracteres");

    rerender(
      <SelectionToolbar
        selectionLength={0}
        aiAvailable
        onRewrite={vi.fn()}
        onTone={vi.fn()}
        onGround={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("selection-toolbar")).not.toBeInTheDocument();
  });

  it("sem IA configurada, a barra não aparece nem com seleção (regra 11)", () => {
    render(
      <SelectionToolbar
        selectionLength={42}
        aiAvailable={false}
        onRewrite={vi.fn()}
        onTone={vi.fn()}
        onGround={vi.fn()}
      />,
    );

    expect(screen.queryByTestId("selection-toolbar")).not.toBeInTheDocument();
  });
});

describe("ReviewChecklistPanel", () => {
  it("mostra os cinco eixos e deixa claro que não alterou o texto (regras 5 e 6)", () => {
    render(
      <ReviewChecklistPanel
        items={[
          { topic: "estrutura", label: "Estrutura da peça", status: "ok", note: "Completa." },
          {
            topic: "fundamentacao",
            label: "Fundamentação",
            status: "nao_avaliado",
            note: "O modelo não avaliou este ponto.",
          },
          {
            topic: "pedidos",
            label: "Pedidos",
            status: "problema",
            note: "Falta o pedido de justiça gratuita.",
          },
          {
            topic: "coerencia",
            label: "Coerência de datas e valores",
            status: "atencao",
            note: "Conferir a data do contrato.",
          },
          { topic: "linguagem", label: "Linguagem", status: "ok", note: "Clara." },
        ]}
      />,
    );

    expect(screen.getByTestId("review-pedidos")).toHaveTextContent("justiça gratuita");
    expect(screen.getByTestId("review-fundamentacao")).toHaveTextContent("Não avaliado");
    expect(screen.getByTestId("review-checklist")).toHaveTextContent("não altera o documento");
    // Regra 6: nada de "corrigir tudo" — corrigir é do usuário.
    expect(screen.queryByRole("button", { name: /corrigir/i })).not.toBeInTheDocument();
  });
});

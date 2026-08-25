import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AIActionPreview } from "@/features/ai/AIActionPreview";

describe("AIActionPreview", () => {
  it("destaca campo novo e campo alterado de formas diferentes (spec 084, regra 2)", () => {
    render(
      <AIActionPreview
        preview={{
          affected_type: "customer",
          summary: "Atualizar o contato Ana",
          changes: {
            notes: { after: "Cliente VIP" },
            city: { before: "Santos", after: "Campinas" },
          },
        }}
      />,
    );

    // Campo que nasce: só o valor novo, marcado como criação.
    const novo = screen.getByTestId("change-notes");
    expect(novo).toHaveAttribute("data-kind", "created");
    expect(novo).toHaveTextContent("Cliente VIP");

    // Campo que muda: o anterior aparece junto — é o que se olha antes de aprovar.
    const alterado = screen.getByTestId("change-city");
    expect(alterado).toHaveAttribute("data-kind", "updated");
    expect(alterado).toHaveTextContent("Santos");
    expect(alterado).toHaveTextContent("Campinas");
  });

  it("deixa claro que nada foi gravado ainda (regra 1)", () => {
    render(<AIActionPreview preview={{ summary: "Criar contato", changes: {} }} />);

    expect(screen.getByText(/Nada foi gravado ainda/)).toBeInTheDocument();
  });

  it("confirmar e recusar chamam quem decide, não a IA", async () => {
    const onApprove = vi.fn().mockResolvedValue(undefined);
    const onReject = vi.fn().mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(
      <AIActionPreview
        preview={{ summary: "Criar tarefa", changes: { task_type: { after: "Contestação" } } }}
        onApprove={onApprove}
        onReject={onReject}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Confirmar" }));
    await user.click(screen.getByRole("button", { name: "Recusar" }));

    expect(onApprove).toHaveBeenCalledOnce();
    expect(onReject).toHaveBeenCalledOnce();
  });

  it("sem callbacks, é só histórico — não oferece botão de decidir", () => {
    render(<AIActionPreview preview={{ summary: "Criou o contato", changes: {} }} />);

    expect(screen.queryByRole("button", { name: "Confirmar" })).not.toBeInTheDocument();
  });
});

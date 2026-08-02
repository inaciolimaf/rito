import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TimelineItem as TimelineItemData } from "@/features/lawsuits/api";
import { TimelineItem } from "@/features/lawsuits/TimelineItem";

function item(kind: TimelineItemData["kind"]): TimelineItemData {
  return {
    kind,
    id: "00000000-0000-0000-0000-000000000001",
    occurred_at: "2026-07-01T12:00:00Z",
    title: "Evento de teste",
    summary: "Resumo do evento",
    actor: null,
    metadata: { header: null, external_code: null },
  };
}

describe("TimelineItem", () => {
  it("renderiza o selo correto para cada tipo", () => {
    render(
      <ul>
        <TimelineItem item={item("task")} />
        <TimelineItem item={item("movement_auto")} />
        <TimelineItem item={item("movement_manual")} />
        <TimelineItem item={item("publication")} />
        <TimelineItem item={item("transaction")} />
      </ul>,
    );

    expect(screen.getByText("Tarefa")).toBeInTheDocument();
    expect(screen.getByText("Andamento")).toBeInTheDocument();
    expect(screen.getByText("Movimentação manual")).toBeInTheDocument();
    expect(screen.getByText("Publicação")).toBeInTheDocument();
    expect(screen.getByText("Financeiro")).toBeInTheDocument();
    expect(screen.getAllByText("Evento de teste")).toHaveLength(5);
  });

  it("mostra o cabeçalho do tribunal quando não há ator humano", () => {
    const tribunal = {
      ...item("movement_auto"),
      metadata: { header: "TJSP - Tribunal de Justiça de São Paulo", external_code: 123 },
    };
    render(
      <ul>
        <TimelineItem item={tribunal} />
      </ul>,
    );
    expect(screen.getByText("TJSP - Tribunal de Justiça de São Paulo")).toBeInTheDocument();
  });
});

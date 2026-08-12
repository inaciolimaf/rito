import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { KanbanBoard, type KanbanColumnDef } from "@/components/domain/KanbanBoard";

interface FakeItem {
  id: string;
  title: string;
}

const COLUMNS: KanbanColumnDef[] = [
  { id: "1", label: "Marketing", total: 1 },
  { id: "2", label: "Negociação", total: 0 },
];

const ITEMS_BY_COLUMN: Record<string, FakeItem[]> = {
  "1": [{ id: "card-1", title: "Processo A" }],
  "2": [],
};

describe("KanbanBoard", () => {
  it("renderiza as colunas e os cards com dados falsos, sem conhecer domínio", () => {
    render(
      <KanbanBoard<FakeItem>
        columns={COLUMNS}
        itemsByColumn={ITEMS_BY_COLUMN}
        getItemId={(item) => item.id}
        onMove={vi.fn()}
        renderCard={(item) => <span>{item.title}</span>}
        emptyColumnMessage="Nenhum processo"
      />,
    );

    expect(screen.getByLabelText("Marketing")).toBeInTheDocument();
    expect(screen.getByLabelText("Negociação")).toBeInTheDocument();
    expect(screen.getByText("Processo A")).toBeInTheDocument();
    expect(screen.getByText("Nenhum processo")).toBeInTheDocument();
  });

  it("arrastar um card de uma coluna pra outra chama onMove com from/to corretos", () => {
    const onMove = vi.fn();
    render(
      <KanbanBoard<FakeItem>
        columns={COLUMNS}
        itemsByColumn={ITEMS_BY_COLUMN}
        getItemId={(item) => item.id}
        onMove={onMove}
        renderCard={(item) => <span>{item.title}</span>}
      />,
    );

    const card = screen.getByTestId("kanban-card-card-1");
    const targetColumn = screen.getByTestId("kanban-column-2");

    fireEvent.dragStart(card);
    fireEvent.dragOver(targetColumn);
    fireEvent.drop(targetColumn);

    expect(onMove).toHaveBeenCalledTimes(1);
    expect(onMove).toHaveBeenCalledWith("card-1", "1", "2");
  });
});

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DataTable } from "@/components/domain/DataTable";
import type { DataTableColumn } from "@/components/domain/types";

interface Row {
  id: string;
  name: string;
}

const rows: Row[] = [
  { id: "1", name: "Ana" },
  { id: "2", name: "Bruno" },
];

const columns: DataTableColumn<Row>[] = [
  { id: "name", header: "Nome", cell: (row) => row.name, sortable: true },
];

describe("DataTable", () => {
  it("renderiza linhas e ordena ao clicar no cabeçalho", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();

    render(
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        sort={null}
        onSortChange={onSortChange}
      />,
    );

    expect(screen.getByText("Ana")).toBeInTheDocument();
    expect(screen.getByText("Bruno")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /nome/i }));
    expect(onSortChange).toHaveBeenCalledWith("name");
  });

  it("seleciona linhas e permite ação em massa", async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();
    const onBulkAction = vi.fn();

    render(
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        selectedIds={new Set(["1"])}
        onSelectionChange={onSelectionChange}
        bulkActions={[{ label: "Arquivar", onClick: onBulkAction }]}
      />,
    );

    expect(screen.getByRole("button", { name: "Arquivar" })).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: "Selecionar linha 2" }));
    expect(onSelectionChange).toHaveBeenCalledWith(new Set(["1", "2"]));
  });

  it("pagina por cursor via anterior/próxima", async () => {
    const user = userEvent.setup();
    const onNextPage = vi.fn();
    const onPreviousPage = vi.fn();

    render(
      <DataTable
        columns={columns}
        data={rows}
        getRowId={(row) => row.id}
        pagination={{
          hasNextPage: true,
          hasPreviousPage: false,
          onNextPage,
          onPreviousPage,
        }}
      />,
    );

    expect(screen.getByRole("button", { name: "Anterior" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Próxima" }));
    expect(onNextPage).toHaveBeenCalledOnce();
  });

  it("mostra estado vazio quando não há dados", () => {
    render(
      <DataTable
        columns={columns}
        data={[]}
        getRowId={(row: Row) => row.id}
        emptyMessage="Nenhum item."
      />,
    );
    expect(screen.getByText("Nenhum item.")).toBeInTheDocument();
  });

  it("mostra estado de erro", () => {
    render(
      <DataTable
        columns={columns}
        data={[]}
        getRowId={(row: Row) => row.id}
        error="Falha ao buscar."
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Falha ao buscar.");
  });
});

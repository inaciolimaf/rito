import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DataTable, VIRTUALIZATION_THRESHOLD } from "@/components/domain/DataTable";
import type { DataTableColumn } from "@/components/domain/types";

interface Row {
  id: string;
  name: string;
}

const columns: DataTableColumn<Row>[] = [{ id: "name", header: "Nome", cell: (row) => row.name }];

function fabricar(quantidade: number): Row[] {
  return Array.from({ length: quantidade }, (_, i) => ({ id: String(i), name: `Pessoa ${i}` }));
}

/** Linhas de dado, sem contar cabeçalho nem espaçador. */
function linhasRenderizadas(): number {
  return screen.getAllByRole("row").filter((tr) => tr.getAttribute("aria-hidden") === null).length;
}

describe("DataTable — virtualização (spec 098, regra 8)", () => {
  it("renderiza a lista inteira quando ela cabe no limite", () => {
    const dados = fabricar(VIRTUALIZATION_THRESHOLD);

    render(<DataTable columns={columns} data={dados} getRowId={(row) => row.id} />);

    // +1 do cabeçalho. Abaixo do limite, virtualizar cobraria complexidade sem devolver
    // nada — e o teste garante que a tabela pequena continua simples.
    expect(linhasRenderizadas()).toBe(dados.length + 1);
    expect(screen.queryByTestId("datatable-spacer-bottom")).not.toBeInTheDocument();
  });

  it("acima do limite renderiza só a janela, não as mil linhas", () => {
    const dados = fabricar(1_000);

    render(<DataTable columns={columns} data={dados} getRowId={(row) => row.id} />);

    const renderizadas = linhasRenderizadas();
    expect(renderizadas).toBeGreaterThan(0);
    expect(renderizadas).toBeLessThan(100);
    expect(screen.getByText("Pessoa 0")).toBeInTheDocument();
    expect(screen.queryByText("Pessoa 999")).not.toBeInTheDocument();
  });

  it("o espaçador preserva a altura total para a barra de rolagem não mentir", () => {
    const dados = fabricar(1_000);

    render(<DataTable columns={columns} data={dados} getRowId={(row) => row.id} />);

    const espacador = screen.getByTestId("datatable-spacer-bottom").firstElementChild;
    // Sem o espaçador, a barra de rolagem encolheria para o tamanho da janela e passar
    // da primeira tela ficaria impossível.
    expect(Number.parseInt((espacador as HTMLElement).style.height, 10)).toBeGreaterThan(1_000);
  });

  it("rolar troca a janela pelas linhas de baixo", () => {
    const dados = fabricar(1_000);
    const { container } = render(
      <DataTable columns={columns} data={dados} getRowId={(row) => row.id} />,
    );
    const viewport = container.querySelector("[data-virtualized]") as HTMLElement;

    fireEvent.scroll(viewport, { target: { scrollTop: 41 * 500 } });

    expect(screen.queryByText("Pessoa 0")).not.toBeInTheDocument();
    expect(screen.getByText("Pessoa 500")).toBeInTheDocument();
  });
});

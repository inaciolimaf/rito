import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DataTable } from "@/components/domain/DataTable";
import { FormModal } from "@/components/domain/FormModal";
import type { DataTableColumn } from "@/components/domain/types";

interface Row {
  id: string;
  name: string;
}

const columns: DataTableColumn<Row>[] = [
  { id: "name", header: "Nome", cell: (row) => row.name, sortable: true },
];

describe("navegação por teclado", () => {
  it("Tab percorre o checkbox de seleção e o cabeçalho ordenável do DataTable", async () => {
    const user = userEvent.setup();
    render(
      <DataTable
        columns={columns}
        data={[{ id: "1", name: "Ana" }]}
        getRowId={(row) => row.id}
        selectedIds={new Set()}
        onSelectionChange={vi.fn()}
        onSortChange={vi.fn()}
      />,
    );

    await user.tab();
    expect(screen.getByRole("checkbox", { name: "Selecionar todos" })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("button", { name: /nome/i })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("checkbox", { name: "Selecionar linha 1" })).toHaveFocus();
  });

  it("Tab percorre o campo e os botões do FormModal, Escape fecha", async () => {
    const user = userEvent.setup();
    const schema = z.object({ name: z.string() });
    const onOpenChange = vi.fn();

    render(
      <FormModal
        open
        onOpenChange={onOpenChange}
        title="Novo item"
        schema={schema}
        defaultValues={{ name: "" }}
        onSubmit={vi.fn()}
      >
        {(form) => (
          <div>
            <Label htmlFor="name">Nome</Label>
            <Input id="name" {...form.register("name")} />
          </div>
        )}
      </FormModal>,
    );

    const nameInput = screen.getByLabelText("Nome");
    nameInput.focus();
    expect(nameInput).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("button", { name: "Cancelar" })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("button", { name: "Salvar" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});

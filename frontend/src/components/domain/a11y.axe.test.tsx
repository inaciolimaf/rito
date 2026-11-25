import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { z } from "zod";

import { ConfirmDialog } from "@/components/domain/ConfirmDialog";
import { DataTable } from "@/components/domain/DataTable";
import { EmptyState } from "@/components/domain/EmptyState";
import { EntityPicker } from "@/components/domain/EntityPicker";
import { FilterBar } from "@/components/domain/FilterBar";
import { FormModal } from "@/components/domain/FormModal";
import { KanbanBoard, type KanbanColumnDef } from "@/components/domain/KanbanBoard";
import { StagnantBadge } from "@/components/domain/StagnantBadge";
import { StatCard } from "@/components/domain/StatCard";
import { TabBar } from "@/components/domain/TabBar";
import type { DataTableColumn, FilterFieldDef } from "@/components/domain/types";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// jest-axe não traz tipos do Vitest: o matcher é declarado aqui, no mesmo estilo do README.
expect.extend(toHaveNoViolations);
declare module "vitest" {
  interface Assertion<T = unknown> {
    toHaveNoViolations(): T;
  }
}

/**
 * Os guardas de foco do Radix (`data-radix-focus-guard`, sentinelas de Tab fora do diálogo) são
 * `aria-hidden` com `tabindex=0`: o axe acusa `aria-hidden-focus` nelas, mas são internas do
 * Radix e não existem para o usuário. Tiram-se só no teste, antes da varredura.
 */
function withoutRadixFocusGuards(): HTMLElement {
  document.querySelectorAll("[data-radix-focus-guard]").forEach((guard) => guard.remove());
  return document.body;
}

/**
 * Guarantee de WCAG 2.2 AA por componente de domínio (references/guarantees.md, "No accessibility
 * violation"). `color-contrast` fica de fora: o jsdom não calcula cores de verdade, e o contraste
 * dos pares de texto é coberto por `src/index.contrast.test.ts` sobre os tokens. `region` fica de
 * fora porque é regra de página inteira, não de componente.
 */
const AXE_OPTIONS = {
  rules: {
    "color-contrast": { enabled: false },
    region: { enabled: false },
  },
};

interface Row {
  id: string;
  name: string;
}

const columns: DataTableColumn<Row>[] = [
  { id: "name", header: "Nome", cell: (row) => row.name, sortable: true },
];

const FILTERS: FilterFieldDef[] = [
  { key: "status", label: "Situação", type: "select", options: [{ value: "a", label: "Ativo" }] },
  { key: "q", label: "Busca", type: "text" },
];

const KANBAN_COLUMNS: KanbanColumnDef[] = [
  { id: "1", label: "Novo", total: 1 },
  { id: "2", label: "Em andamento", total: 0 },
];

describe("axe nos componentes de domínio", () => {
  it("DataTable com ordenação, seleção, ações de linha e exportação", async () => {
    const { container } = render(
      <DataTable
        columns={columns}
        data={[{ id: "1", name: "Ana" }]}
        getRowId={(row) => row.id}
        selectedIds={new Set()}
        onSelectionChange={vi.fn()}
        onSortChange={vi.fn()}
        sort={{ field: "name", order: "asc" }}
        onExport={vi.fn()}
        rowActions={() => <button type="button">Editar</button>}
        pagination={{
          hasPreviousPage: false,
          hasNextPage: true,
          onPreviousPage: vi.fn(),
          onNextPage: vi.fn(),
        }}
        selectable
      />,
    );
    expect(await axe(container, AXE_OPTIONS)).toHaveNoViolations();
  });

  it("DataTable vazio e com erro", async () => {
    const { container } = render(
      <>
        <DataTable
          columns={columns}
          data={[]}
          getRowId={(row) => row.id}
          selectedIds={new Set()}
          onSelectionChange={vi.fn()}
        />
        <EmptyState title="Não foi possível carregar os dados." role="alert" />
      </>,
    );
    expect(await axe(container, AXE_OPTIONS)).toHaveNoViolations();
  });

  it("FormModal aberto com campo rotulado e botões", async () => {
    render(
      <FormModal
        open
        onOpenChange={vi.fn()}
        title="Novo item"
        schema={z.object({ name: z.string() })}
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
    expect(await axe(withoutRadixFocusGuards(), AXE_OPTIONS)).toHaveNoViolations();
  });

  it("ConfirmDialog com confirmação digitada", async () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={vi.fn()}
        title="Excluir processo"
        description="Esta ação não pode ser desfeita."
        destructive
        requireTypedConfirmation="EXCLUIR"
        onConfirm={vi.fn()}
      />,
    );
    expect(await axe(withoutRadixFocusGuards(), AXE_OPTIONS)).toHaveNoViolations();
  });

  it("FilterBar com seletor e campo de texto", async () => {
    const { container } = render(
      <MemoryRouter>
        <FilterBar fields={FILTERS} />
      </MemoryRouter>,
    );
    expect(await axe(container, AXE_OPTIONS)).toHaveNoViolations();
  });

  it("EntityPicker com um item selecionado", async () => {
    const { container } = render(
      <EntityPicker
        label="Cliente"
        value={[{ id: "1", label: "Ana Souza" }]}
        onChange={vi.fn()}
        onSearch={vi.fn().mockResolvedValue([])}
        multiple
      />,
    );
    expect(await axe(container, AXE_OPTIONS)).toHaveNoViolations();
  });

  it("KanbanBoard com cards e coluna vazia", async () => {
    const { container } = render(
      <KanbanBoard<{ id: string; title: string }>
        columns={KANBAN_COLUMNS}
        itemsByColumn={{ "1": [{ id: "c1", title: "Processo A" }], "2": [] }}
        getItemId={(item) => item.id}
        onMove={vi.fn()}
        renderCard={(item) => <span>{item.title}</span>}
      />,
    );
    expect(await axe(container, AXE_OPTIONS)).toHaveNoViolations();
  });

  it("TabBar, StatCard, StagnantBadge", async () => {
    const { container } = render(
      <MemoryRouter>
        <TabBar
          ariaLabel="Seções"
          active="a"
          onSelect={vi.fn()}
          items={[
            { value: "a", label: "Dados" },
            { value: "b", label: "Histórico" },
          ]}
        />
        <StatCard label="Processos ativos" value={12} />
        <StagnantBadge daysInStage={9} stagnantDays={7} />
      </MemoryRouter>,
    );
    expect(await axe(container, AXE_OPTIONS)).toHaveNoViolations();
    expect(screen.getByTestId("stagnant-badge")).toHaveAttribute("aria-describedby");
  });
});

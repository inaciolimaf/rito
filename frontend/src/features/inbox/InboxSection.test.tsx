import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { InboxSection } from "@/features/inbox/InboxSection";
import type { InboxRow } from "@/features/inbox/api";

const { mockListInbox } = vi.hoisted(() => ({
  mockListInbox: vi.fn(),
}));

vi.mock("@/features/inbox/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/features/inbox/api")>();
  return { ...original, listInbox: mockListInbox };
});

const ROW: InboxRow = {
  post_id: "p1",
  lawsuit_id: "l1",
  task_type_name: "CONTESTAÇÃO SIMPLES",
  scheduled_date: "2026-08-10",
  scheduled_time: null,
  deadline_date: "2026-08-15",
  is_urgent: false,
  is_important: false,
  is_private: false,
  is_read: false,
  is_starred: false,
  created_at: "2026-08-03T10:00:00Z",
  parties: ["Cliente A"],
  assignee_names: ["Usuário de Teste"],
};

function renderSection(collapsed: boolean, onToggleCollapsed = vi.fn()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    onToggleCollapsed,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <InboxSection
            section="unread"
            count={1}
            collapsed={collapsed}
            onToggleCollapsed={onToggleCollapsed}
            selectedIds={new Set()}
            onToggleRow={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

describe("InboxSection", () => {
  beforeEach(() => {
    mockListInbox.mockReset();
    mockListInbox.mockResolvedValue({ items: [ROW], next_cursor: null });
  });

  it("colapsada não carrega as tarefas; expandir carrega e mostra as colunas", async () => {
    const user = userEvent.setup();
    const { onToggleCollapsed } = renderSection(true);

    // Colapsada: o cabeçalho mostra o contador e NADA é buscado (economia de query).
    expect(screen.getByText("Não lidas")).toBeInTheDocument();
    expect(screen.getByText(/1 ▸/)).toBeInTheDocument();
    expect(mockListInbox).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: /Não lidas/ }));
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });

  it("expandida mostra a tarefa com partes, prazo e responsáveis", async () => {
    renderSection(false);

    await waitFor(() => expect(screen.getByText("CONTESTAÇÃO SIMPLES")).toBeInTheDocument());
    expect(screen.getByText("Cliente A")).toBeInTheDocument();
    expect(screen.getByText("15/08/2026")).toBeInTheDocument();
    expect(screen.getByText("Usuário de Teste")).toBeInTheDocument();
  });
});

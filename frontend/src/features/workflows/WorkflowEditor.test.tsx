import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowDetail, WorkflowPayload } from "@/features/workflows/api";
import { WorkflowEditor } from "@/features/workflows/WorkflowEditor";

vi.mock("@/features/users/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/features/users/api")>();
  return {
    ...original,
    listUsers: vi.fn().mockResolvedValue({ items: [], next_cursor: null, total: 0 }),
  };
});

vi.mock("@/features/task-types/api", () => ({
  listTaskTypes: vi.fn().mockResolvedValue({
    items: [
      {
        id: "tt-a",
        name: "ANÁLISE",
        reward: 8,
        is_active: true,
        is_system: false,
        step_id: null,
        step_name: null,
        complexity: "SIMPLES",
        duration: "MIN_15",
        show_in_schedule: false,
        last_assigned_at: null,
        created_at: "2026-08-01T00:00:00Z",
      },
    ],
    total: 1,
  }),
}));

const INITIAL: WorkflowDetail = {
  id: "wf-1",
  name: "Fluxo teste",
  is_active: true,
  steps: [
    {
      task_type_id: "tt-a",
      task_type_name: "ANÁLISE",
      user_id: null,
      user_name: null,
      days_offset: 0,
    },
    {
      task_type_id: "tt-b",
      task_type_name: "PEÇA",
      user_id: null,
      user_name: null,
      days_offset: 3,
    },
    {
      task_type_id: "tt-c",
      task_type_name: "PROTOCOLO",
      user_id: null,
      user_name: null,
      days_offset: null,
    },
  ],
};

function renderEditor(onSubmit: (payload: WorkflowPayload) => Promise<void>): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <WorkflowEditor open onOpenChange={() => undefined} initial={INITIAL} onSubmit={onSubmit} />
    </QueryClientProvider>,
  );
}

describe("WorkflowEditor (spec 038)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renderiza as etapas na ordem inicial", () => {
    renderEditor(vi.fn().mockResolvedValue(undefined));
    expect(screen.getAllByTestId("workflow-step-row")).toHaveLength(3);
    expect(screen.getByLabelText("Mover etapa 1 para baixo")).toBeEnabled();
    expect(screen.getByLabelText("Mover etapa 1 para cima")).toBeDisabled();
  });

  it("reordena etapas com os botões de mover (regra 11)", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderEditor(onSubmit);

    // Sobe a etapa 2 para a primeira posição: ordem vira [B, A, C].
    await userEvent.click(screen.getByLabelText("Mover etapa 2 para cima"));
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const call = onSubmit.mock.calls[0] as unknown as [WorkflowPayload];
    expect(call[0].steps.map((step) => step.task_type_id)).toEqual(["tt-b", "tt-a", "tt-c"]);
  });

  it("dias_offset vazio vira null (regra 4) no submit", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderEditor(onSubmit);
    await userEvent.click(screen.getByRole("button", { name: "Salvar" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    const call = onSubmit.mock.calls[0] as unknown as [WorkflowPayload];
    expect(call[0].steps.map((step) => step.days_offset)).toEqual([0, 3, null]);
  });
});

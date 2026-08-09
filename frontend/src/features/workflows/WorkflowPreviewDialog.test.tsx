import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { WorkflowPreview } from "@/features/workflows/api";
import { WorkflowPreviewDialog } from "@/features/workflows/WorkflowPreviewDialog";

const { mockPreview, mockApply } = vi.hoisted(() => ({
  mockPreview: vi.fn(),
  mockApply: vi.fn(),
}));

vi.mock("@/features/workflows/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/features/workflows/api")>();
  return { ...original, previewWorkflow: mockPreview, applyWorkflow: mockApply };
});

const LAWSUIT = { id: "l-1", label: "Cliente A — 0000000-00.2026.8.00.0000" };

const PREVIEW: WorkflowPreview = {
  tasks: [
    { task_type_name: "ANÁLISE", user_id: "u-1", user_name: "Gestor", date: "2026-08-10" },
    { task_type_name: "PEÇA", user_id: "u-1", user_name: "Gestor", date: "2026-08-13" },
  ],
  skipped: [{ task_type_name: "ARQUIVO", reason: "Tipo de tarefa inativo" }],
  already_applied: false,
};

function renderDialog(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <WorkflowPreviewDialog
        open
        onOpenChange={() => undefined}
        workflowId="wf-1"
        lawsuit={LAWSUIT}
      />
    </QueryClientProvider>,
  );
}

describe("WorkflowPreviewDialog (spec 038)", () => {
  beforeEach(() => {
    mockPreview.mockResolvedValue(PREVIEW);
    mockApply.mockResolvedValue({ created: 2, post_ids: ["p1", "p2"], skipped: [] });
  });

  it("lista as tarefas do preview (regra 6) e aplica sem confirmação extra", async () => {
    renderDialog();

    expect(await screen.findByText("ANÁLISE")).toBeInTheDocument();
    expect(screen.getByText("PEÇA")).toBeInTheDocument();
    expect(screen.getByText(/10\/08\/2026/)).toBeInTheDocument();
    expect(screen.getByText(/Tipo de tarefa inativo/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Aplicar workflow" }));
    await waitFor(() => expect(mockApply).toHaveBeenCalledWith("wf-1", "l-1", false));
    expect(await screen.findByTestId("workflow-applied-message")).toHaveTextContent(
      "2 tarefa(s) criada(s)",
    );
  });

  it("reaplicação avisa e pede confirmação extra (regra 8)", async () => {
    mockPreview.mockResolvedValue({ ...PREVIEW, already_applied: true });
    renderDialog();

    expect(await screen.findByTestId("workflow-already-applied")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Aplicar mesmo assim" }));
    await waitFor(() => expect(mockApply).toHaveBeenCalledWith("wf-1", "l-1", true));
  });
});

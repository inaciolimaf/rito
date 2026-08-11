import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SuggestWorkflowDialog } from "@/features/crm/SuggestWorkflowDialog";
import type { WorkflowPreview } from "@/features/workflows/api";

const { mockPreview, mockApply, mockSuppress } = vi.hoisted(() => ({
  mockPreview: vi.fn(),
  mockApply: vi.fn(),
  mockSuppress: vi.fn(),
}));

vi.mock("@/features/workflows/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/features/workflows/api")>();
  return { ...original, previewWorkflow: mockPreview };
});

vi.mock("@/features/crm/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/features/crm/api")>();
  return { ...original, applyLawsuitWorkflow: mockApply, suppressLawsuitWorkflow: mockSuppress };
});

const PREVIEW: WorkflowPreview = {
  tasks: [{ task_type_name: "ANÁLISE", user_id: "u-1", user_name: "Gestor", date: "2026-08-13" }],
  skipped: [],
  already_applied: false,
};

function renderDialog(onSuppressed = () => undefined): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <SuggestWorkflowDialog
        open
        onOpenChange={() => undefined}
        workflowId="wf-1"
        workflowName="Fluxo Negociação"
        lawsuit={{ id: "l-1", label: "Cliente A — 0000000-00.2026.8.00.0000" }}
        stageId="stage-1"
        onSuppressed={onSuppressed}
      />
    </QueryClientProvider>,
  );
}

describe("SuggestWorkflowDialog (spec 053)", () => {
  beforeEach(() => {
    mockPreview.mockResolvedValue(PREVIEW);
    mockApply.mockResolvedValue({ created: 1, post_ids: ["p1"], skipped: [] });
  });

  it("mostra o preview com datas e aplica via /lawsuits/{id}/apply-workflow, com a etapa", async () => {
    renderDialog();

    expect(await screen.findByText("ANÁLISE")).toBeInTheDocument();
    expect(screen.getByText(/13\/08\/2026/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Aplicar workflow" }));
    await waitFor(() => expect(mockApply).toHaveBeenCalledWith("wf-1", "l-1", false, "stage-1"));
  });

  it('"não sugerir novamente" grava a supressão e fecha', async () => {
    const onSuppressed = vi.fn();
    mockSuppress.mockResolvedValue(undefined);
    renderDialog(onSuppressed);

    await screen.findByText("ANÁLISE");
    await userEvent.click(screen.getByRole("button", { name: "Não sugerir novamente" }));

    await waitFor(() => expect(mockSuppress).toHaveBeenCalledWith("l-1", "stage-1"));
    await waitFor(() => expect(onSuppressed).toHaveBeenCalled());
  });
});

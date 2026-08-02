import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { StageStepSelect } from "@/features/lawsuits/StageStepSelect";

vi.mock("@/features/stages/api", () => ({
  listSteps: vi.fn().mockResolvedValue([
    { id: 1, name: "Marketing", position: 1 },
    { id: 2, name: "Negociação", position: 2 },
  ]),
  listStages: vi.fn((params: { step_id?: number }) => {
    const items =
      params.step_id === 1
        ? [{ id: "stage-marketing", name: "Fazendo Contato", step_id: 1, step_name: "Marketing" }]
        : [{ id: "stage-negociacao", name: "Em Negociação", step_id: 2, step_name: "Negociação" }];
    return Promise.resolve({ items, next_cursor: null, total: items.length });
  }),
}));

function Harness(): JSX.Element {
  const [value, setValue] = React.useState("");
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <StageStepSelect value={value} onChange={setValue} />
    </QueryClientProvider>
  );
}

describe("StageStepSelect", () => {
  it("etapa filtra por fase — trocar a fase mostra só as etapas daquela fase", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Marketing" })).toBeInTheDocument(),
    );

    await user.selectOptions(screen.getByLabelText("Fase"), "1");
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Fazendo Contato" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("option", { name: "Em Negociação" })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Fase"), "2");
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Em Negociação" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("option", { name: "Fazendo Contato" })).not.toBeInTheDocument();
  });

  it("trocar a fase limpa a etapa escolhida", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Marketing" })).toBeInTheDocument(),
    );
    await user.selectOptions(screen.getByLabelText("Fase"), "1");
    await waitFor(() => expect(screen.getByLabelText("Etapa")).toHaveValue(""));
    await user.selectOptions(screen.getByLabelText("Etapa"), "stage-marketing");
    expect(screen.getByLabelText("Etapa")).toHaveValue("stage-marketing");

    await user.selectOptions(screen.getByLabelText("Fase"), "2");

    await waitFor(() => expect(screen.getByLabelText("Etapa")).toHaveValue(""));
  });
});

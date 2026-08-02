import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import { LawsuitForm } from "@/features/lawsuits/LawsuitForm";
import { DEFAULT_LAWSUIT_FORM_VALUES, type LawsuitFormValues } from "@/features/lawsuits/schema";

vi.mock("@/features/action-groups/api", () => ({
  listActionGroups: vi.fn().mockResolvedValue({
    items: [
      { id: "group-civel", name: "Cível", is_active: true, lawsuit_types_count: 1 },
      { id: "group-trabalhista", name: "Trabalhista", is_active: true, lawsuit_types_count: 1 },
    ],
    next_cursor: null,
    total: 2,
  }),
}));

vi.mock("@/features/lawsuit-types/api", () => ({
  listLawsuitTypes: vi.fn((params: { group_id?: string }) => {
    const items =
      params.group_id === "group-civel"
        ? [{ id: "type-posse", name: "Reintegração de Posse", action_group_id: "group-civel" }]
        : [{ id: "type-reclamatoria", name: "Reclamatória", action_group_id: "group-trabalhista" }];
    return Promise.resolve({ items, next_cursor: null, total: items.length });
  }),
}));

vi.mock("@/features/courts/api", () => ({
  listCourts: vi.fn().mockResolvedValue([]),
  listCourtSystems: vi.fn().mockResolvedValue([]),
}));

vi.mock("@/features/stages/api", () => ({
  listSteps: vi.fn().mockResolvedValue([]),
  listStages: vi.fn().mockResolvedValue({ items: [], next_cursor: null, total: 0 }),
}));

function Harness(): JSX.Element {
  const form = useForm<LawsuitFormValues>({ defaultValues: DEFAULT_LAWSUIT_FORM_VALUES });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return (
    <QueryClientProvider client={queryClient}>
      <LawsuitForm
        form={form}
        onSearchUsers={() => Promise.resolve([])}
        onSearchCustomers={() => Promise.resolve([])}
        currentResponsible={null}
        currentCourt={null}
      />
    </QueryClientProvider>
  );
}

describe("LawsuitForm", () => {
  it("tipo filtra por grupo — trocar o grupo mostra só os tipos daquele grupo", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await waitFor(() => expect(screen.getByRole("option", { name: "Cível" })).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText("Grupo de ação"), "group-civel");
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Reintegração de Posse" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("option", { name: "Reclamatória" })).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Grupo de ação"), "group-trabalhista");
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "Reclamatória" })).toBeInTheDocument(),
    );
    expect(screen.queryByRole("option", { name: "Reintegração de Posse" })).not.toBeInTheDocument();
  });
});

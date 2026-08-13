import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { VariablePicker } from "@/features/templates/VariablePicker";

const listTemplateVariables = vi.fn().mockResolvedValue([
  { namespace: "cliente", key: "nome_completo", label: "Nome completo" },
  { namespace: "processo", key: "numero_cnj", label: "Número CNJ" },
]);

vi.mock("@/features/templates/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/templates/api")>(
    "@/features/templates/api",
  );
  return {
    ...actual,
    listTemplateVariables: () => listTemplateVariables(),
  };
});

describe("VariablePicker", () => {
  it("insere o token {{namespace.campo}} ao escolher uma variável", async () => {
    const user = userEvent.setup();
    const onInsert = vi.fn();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <VariablePicker onInsert={onInsert} />
      </QueryClientProvider>,
    );

    await screen.findByText("Número CNJ");
    await user.selectOptions(screen.getByLabelText("Inserir variável"), "processo.numero_cnj");

    expect(onInsert).toHaveBeenCalledWith("{{processo.numero_cnj}}");
  });
});

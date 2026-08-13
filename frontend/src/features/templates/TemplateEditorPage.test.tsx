import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { TemplateEditorPage } from "@/features/templates/TemplateEditorPage";

const TEMPLATE = {
  id: "t1",
  name: "Contrato padrão",
  type: "CONTRATO" as const,
  content: "<p>corpo</p>",
  header_content: "",
  footer_content: "",
  watermark_text: null,
  created_by: "u1",
  deleted_at: null,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const getTemplate = vi.fn().mockResolvedValue(TEMPLATE);
const updateTemplate = vi
  .fn()
  .mockImplementation((_id: string, values: object) => Promise.resolve({ ...TEMPLATE, ...values }));

vi.mock("@/features/templates/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/templates/api")>(
    "@/features/templates/api",
  );
  return {
    ...actual,
    getTemplate: (...args: unknown[]) => getTemplate(...(args as [never])),
    updateTemplate: (...args: unknown[]) => updateTemplate(...(args as [never])),
  };
});

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/library/t1"]}>
        <Routes>
          <Route path="/library/:id" element={<TemplateEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TemplateEditorPage", () => {
  it("carrega o modelo e não salva nada antes de o usuário mudar algo", async () => {
    renderPage();

    await screen.findByDisplayValue("Contrato padrão");
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(updateTemplate).not.toHaveBeenCalled();
  });

  it("edita cabeçalho e rodapé (campos fora do corpo) e autosalva depois do debounce", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByDisplayValue("Contrato padrão");
    await user.type(screen.getByLabelText("Cabeçalho"), "Escritório X");
    await user.type(screen.getByLabelText("Rodapé"), "Confidencial");

    await waitFor(
      () => {
        expect(updateTemplate).toHaveBeenCalledWith(
          "t1",
          expect.objectContaining({
            header_content: "Escritório X",
            footer_content: "Confidencial",
          }),
        );
      },
      { timeout: 3000 },
    );
    await screen.findByText("Salvo");
  });
});

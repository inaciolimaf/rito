import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { TemplatesListPage } from "@/features/templates/TemplatesListPage";

const listTemplates = vi.fn().mockImplementation(({ view }: { view?: string }) =>
  Promise.resolve(
    view === "trash"
      ? {
          items: [
            {
              id: "t2",
              name: "Modelo excluído",
              type: "DOCUMENTO",
              content: "",
              created_by: "u1",
              deleted_at: "2026-08-01T00:00:00Z",
              created_at: "2026-08-01T00:00:00Z",
              updated_at: "2026-08-01T00:00:00Z",
            },
          ],
          next_cursor: null,
          total: 1,
        }
      : {
          items: [
            {
              id: "t1",
              name: "Contrato padrão",
              type: "CONTRATO",
              content: "corpo",
              created_by: "u1",
              deleted_at: null,
              created_at: "2026-08-01T00:00:00Z",
              updated_at: "2026-08-01T00:00:00Z",
            },
          ],
          next_cursor: null,
          total: 1,
        },
  ),
);
const restoreTemplate = vi.fn().mockResolvedValue({});
const deleteTemplate = vi.fn().mockResolvedValue(undefined);
const listPublicTemplates = vi.fn().mockResolvedValue([
  {
    id: "p1",
    name: "Contrato de honorários",
    type: "CONTRATO",
    content: "",
    header_content: "",
    footer_content: "",
    watermark_text: null,
    created_at: "2026-08-01T00:00:00Z",
  },
]);
const copyPublicTemplate = vi.fn().mockResolvedValue({ id: "t3" });

vi.mock("@/features/templates/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/templates/api")>(
    "@/features/templates/api",
  );
  return {
    ...actual,
    listTemplates: (...args: unknown[]) => listTemplates(...(args as [never])),
    restoreTemplate: (...args: unknown[]) => restoreTemplate(...(args as [never])),
    deleteTemplate: (...args: unknown[]) => deleteTemplate(...(args as [never])),
    listPublicTemplates: (...args: unknown[]) => listPublicTemplates(...(args as [never])),
    copyPublicTemplate: (...args: unknown[]) => copyPublicTemplate(...(args as [never])),
  };
});

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/library"]}>
        <TemplatesListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TemplatesListPage", () => {
  it("filtra por tipo e mostra a lixeira ao trocar para 'Somente os excluídos'", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Contrato padrão");

    const select = screen.getByLabelText("Tipo");
    await user.selectOptions(select, "trash");

    await screen.findByText("Modelo excluído");
    await screen.findByText("Restaurar");
  });

  it("exclui um modelo (vai para a lixeira) via confirmação", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Contrato padrão");
    await user.click(screen.getByText("Excluir"));

    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Excluir" }));

    await waitFor(() => {
      expect(deleteTemplate).toHaveBeenCalledWith("t1");
    });
  });

  it("troca para a Biblioteca Pública e copia um modelo (spec 068)", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("Contrato padrão");
    await user.click(screen.getByRole("tab", { name: "Biblioteca Pública" }));

    await screen.findByText("Contrato de honorários");
    await user.click(screen.getByText("Copiar para meus modelos"));

    await waitFor(() => {
      expect(copyPublicTemplate).toHaveBeenCalledWith("p1");
    });
  });
});

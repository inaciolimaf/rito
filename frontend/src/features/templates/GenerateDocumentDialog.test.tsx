import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { GenerateDocumentDialog } from "@/features/templates/GenerateDocumentDialog";

const resolveTemplate = vi.fn().mockResolvedValue({
  content: "<p>corpo</p>",
  header_content: "",
  footer_content: "",
  missing: ["cliente.nome_completo"],
});
const generateTemplatePdf = vi.fn().mockResolvedValue(undefined);

vi.mock("@/features/templates/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/templates/api")>(
    "@/features/templates/api",
  );
  return {
    ...actual,
    resolveTemplate: (...args: unknown[]) => resolveTemplate(...(args as [never])),
    generateTemplatePdf: (...args: unknown[]) => generateTemplatePdf(...(args as [never])),
  };
});

function renderDialog(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <GenerateDocumentDialog
        open
        onOpenChange={() => {}}
        templateId="t1"
        templateName="Contrato padrão"
      />
    </QueryClientProvider>,
  );
}

describe("GenerateDocumentDialog", () => {
  it("mostra variável ausente e baixa o PDF ao clicar", async () => {
    const user = userEvent.setup();
    renderDialog();

    await screen.findByText(/Variáveis sem dado: cliente.nome_completo/);
    await user.click(screen.getByRole("button", { name: "Baixar PDF" }));

    await waitFor(() => {
      expect(generateTemplatePdf).toHaveBeenCalledWith(
        "t1",
        { customer_id: null, lawsuit_id: null },
        "Contrato padrão.pdf",
      );
    });
  });

  it("desabilita 'salvar na nuvem' sem processo selecionado", async () => {
    renderDialog();
    await screen.findByText(/Variáveis sem dado/);
    expect(screen.getByRole("button", { name: "Salvar na nuvem do processo" })).toBeDisabled();
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DocumentBrowser } from "@/features/documents/DocumentBrowser";

const folderRoot = {
  id: "f1",
  scope_type: "CUSTOMER" as const,
  scope_id: "c1",
  parent_folder_id: null,
  name: "Contratos",
  created_by: "u1",
  created_at: "2026-08-01T10:00:00Z",
};

const documentRoot = {
  id: "d1",
  scope_type: "CUSTOMER" as const,
  scope_id: "c1",
  folder_id: null,
  filename: "recibo.pdf",
  content_type: "application/pdf",
  size_bytes: 2048,
  uploaded_by: "u1",
  created_at: "2026-08-02T10:00:00Z",
};

const listDocuments = vi
  .fn()
  .mockImplementation(({ folder_id }: { folder_id: string | null }) =>
    Promise.resolve(
      folder_id === null
        ? { folders: [folderRoot], documents: [documentRoot] }
        : { folders: [], documents: [] },
    ),
  );
const uploadDocuments = vi.fn().mockResolvedValue([
  {
    filename: "grande.txt",
    status: "error",
    document: null,
    error: "Quota de armazenamento do plano excedida.",
  },
]);
const searchDocuments = vi.fn().mockResolvedValue([]);

vi.mock("@/features/documents/api", async () => {
  const actual = await vi.importActual<typeof import("@/features/documents/api")>(
    "@/features/documents/api",
  );
  return {
    ...actual,
    listDocuments: (...args: unknown[]) => listDocuments(...(args as [never])),
    uploadDocuments: (...args: unknown[]) => uploadDocuments(...(args as [never])),
    searchDocuments: (...args: unknown[]) => searchDocuments(...(args as [never])),
  };
});

function renderBrowser(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <DocumentBrowser scopeType="CUSTOMER" scopeId="c1" />
    </QueryClientProvider>,
  );
}

describe("DocumentBrowser", () => {
  it("navega para dentro da pasta ao clicar nela", async () => {
    const user = userEvent.setup();
    renderBrowser();

    await screen.findByText("recibo.pdf");
    await user.click(screen.getByText("📁 Contratos"));

    await waitFor(() => {
      expect(listDocuments).toHaveBeenLastCalledWith(expect.objectContaining({ folder_id: "f1" }));
    });
    await screen.findByText("Raiz");
  });

  it("mostra o erro de quota quando o upload falha", async () => {
    const user = userEvent.setup();
    renderBrowser();

    await screen.findByText("recibo.pdf");
    const file = new File(["conteudo"], "grande.txt", { type: "text/plain" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    await screen.findByText(/Quota de armazenamento do plano excedida/);
  });
});

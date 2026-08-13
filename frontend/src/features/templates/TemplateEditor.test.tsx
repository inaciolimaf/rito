import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TemplateEditor } from "@/features/templates/TemplateEditor";

function Wrapper({ onChange }: { onChange: (html: string) => void }): JSX.Element {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <TemplateEditor content="<p>Olá</p>" onChange={onChange} />
    </QueryClientProvider>
  );
}

describe("TemplateEditor", () => {
  it("aplica negrito pela toolbar e propaga o HTML formatado", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Wrapper onChange={onChange} />);

    const editable = await screen.findByText("Olá");
    // O editor autofoca no fim do documento ao montar — não depende de clicar no
    // texto (jsdom não resolve coordenada→posição, `elementFromPoint` é stub).
    // Cursor solto (sem seleção): negrito vira "marca pendente" — aplica ao que for
    // digitado a seguir, mesmo padrão de qualquer editor rico.
    await user.click(screen.getByLabelText("Negrito"));
    await user.type(editable, "!");

    await waitFor(
      () => {
        expect(onChange).toHaveBeenCalledWith(expect.stringContaining("<strong>"));
      },
      { timeout: 3000 },
    );
  });

  it("insere uma tabela pela toolbar", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Wrapper onChange={onChange} />);

    await screen.findByText("Olá");
    await user.click(screen.getByLabelText("Inserir tabela"));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(expect.stringContaining("<table"));
    });
  });

  it("insere quebra de página (linha horizontal)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Wrapper onChange={onChange} />);

    await screen.findByText("Olá");
    await user.click(screen.getByLabelText("Quebra de página"));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(expect.stringContaining("<hr"));
    });
  });
});

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
    await user.click(editable);
    // Seleção EXPLÍCITA antes de formatar (dívida 28). A versão anterior deste teste
    // dependia da "marca pendente": clicar em Negrito com o cursor solto e digitar em
    // seguida. Isso amarrava o teste a duas corridas que o jsdom não resolve — o
    // `autofocus: "end"` do tiptap é assíncrono, e o clique no botão da toolbar tira o
    // foco do contenteditable, cuja seleção o jsdom não restaura. Quando as duas
    // perdiam, o "!" entrava na POSIÇÃO 0 e saía sem negrito: o HTML final era
    // `<p>!Olá</p>`. Medido nesta spec: 1 falha em 8 execuções.
    //
    // `Ctrl+A` é tratado pelo keymap do ProseMirror (`selectAll`), não por coordenada,
    // então não depende de nada disso — e é o que o usuário faz de verdade para negritar
    // um texto que já existe.
    await user.keyboard("{Control>}a{/Control}");
    await user.click(screen.getByLabelText("Negrito"));

    await waitFor(
      () => {
        // Afirma o conteúdo, não só a presença da tag: `<strong>Olá</strong>` prova que o
        // negrito caiu no texto certo. A versão anterior aceitava qualquer `<strong>`.
        expect(onChange).toHaveBeenCalledWith(expect.stringContaining("<strong>Olá</strong>"));
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

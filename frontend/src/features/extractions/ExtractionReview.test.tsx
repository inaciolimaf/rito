import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ExtractionReview } from "@/features/extractions/ExtractionReview";
import type { ExtractionData } from "@/features/extractions/api";

const BASE: ExtractionData = {
  id: "extraction-1",
  filename: "rg-ana.pdf",
  content_type: "application/pdf",
  page_count: 1,
  document_kind: "rg",
  target_type: "customer",
  used_ocr: true,
  ocr_text: "CARTEIRA DE IDENTIDADE\nAna Paula Ribeiro",
  fields: {
    name: { value: "Ana Paula Ribeiro", confidence: 0.97, prefill: true, is_valid: true },
    birth_date: { value: "1988-03-14", confidence: 0.55, prefill: false, is_valid: true },
    identification: { value: "11144477700", confidence: 0.88, prefill: true, is_valid: false },
  },
  status: "pending",
  action_id: null,
  applied_id: null,
  model: "fabricante-x/modelo-y",
  tokens_used: 380,
  created_at: "2026-08-27T12:00:00Z",
  duplicate: null,
};

describe("ExtractionReview", () => {
  it("mostra o documento e os campos lado a lado (spec 091 §6)", () => {
    render(<ExtractionReview extraction={BASE} onApply={vi.fn()} onDiscard={vi.fn()} />);

    expect(screen.getByLabelText("Documento")).toHaveTextContent("rg-ana.pdf");
    expect(screen.getByLabelText("Campos extraídos")).toBeInTheDocument();
    expect(screen.getByLabelText("Nome")).toHaveValue("Ana Paula Ribeiro");
  });

  it("campo de leitura incerta vem VAZIO, com o valor lido ao lado (regra 3)", () => {
    render(<ExtractionReview extraction={BASE} onApply={vi.fn()} onDiscard={vi.fn()} />);

    expect(screen.getByLabelText("Nascimento")).toHaveValue("");
    expect(screen.getByText(/parece dizer/)).toHaveTextContent("1988-03-14");
  });

  it("CPF inválido aparece marcado e ainda assim preenchido (regra 4)", () => {
    render(<ExtractionReview extraction={BASE} onApply={vi.fn()} onDiscard={vi.fn()} />);

    expect(screen.getByLabelText("CPF/CNPJ")).toHaveValue("11144477700");
    expect(screen.getByTitle(/dígito verificador não fecha/)).toHaveTextContent("inválido");
  });

  it("o texto do OCR fica recolhido até alguém precisar dele (regra 10)", async () => {
    const user = userEvent.setup();
    render(<ExtractionReview extraction={BASE} onApply={vi.fn()} onDiscard={vi.fn()} />);

    expect(screen.queryByText(/CARTEIRA DE IDENTIDADE/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Ver o texto lido/ }));
    expect(screen.getByText(/CARTEIRA DE IDENTIDADE/)).toBeInTheDocument();
  });

  it("cadastrar envia o que está na tela, não o que o modelo leu", async () => {
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<ExtractionReview extraction={BASE} onApply={onApply} onDiscard={vi.fn()} />);

    await user.clear(screen.getByLabelText("Nome"));
    await user.type(screen.getByLabelText("Nome"), "Ana P. Ribeiro");
    await user.click(screen.getByRole("button", { name: "Cadastrar" }));

    expect(onApply).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Ana P. Ribeiro", birth_date: "" }),
    );
  });

  it("duplicata avisa antes de criar um segundo cadastro (regra 8)", () => {
    render(
      <ExtractionReview
        extraction={{
          ...BASE,
          duplicate: {
            customer_id: "customer-1",
            name: "Ana Paula Ribeiro",
            identification: "11144477735",
          },
        }}
        onApply={vi.fn()}
        onDiscard={vi.fn()}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Já existe um cadastro");
  });
});

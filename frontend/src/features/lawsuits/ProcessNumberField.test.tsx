import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it, vi } from "vitest";

import type { ProcessNumberValidation } from "@/features/lawsuits/api";
import {
  ProcessNumberField,
  type InferredCourtOption,
} from "@/features/lawsuits/ProcessNumberField";

interface FormValues {
  process_number: string;
}

function validation(partial: Partial<ProcessNumberValidation>): ProcessNumberValidation {
  return {
    valid: true,
    formatted: null,
    parsed: null,
    inferred_court: null,
    error: null,
    ...partial,
  };
}

interface HarnessProps {
  onValidate: (raw: string) => Promise<ProcessNumberValidation>;
  onCourtInferred?: (court: InferredCourtOption) => void;
}

function Harness({ onValidate, onCourtInferred }: HarnessProps): JSX.Element {
  const form = useForm<FormValues>({ defaultValues: { process_number: "" } });
  return (
    <ProcessNumberField
      control={form.control}
      name="process_number"
      onValidate={onValidate}
      onCourtInferred={onCourtInferred}
    />
  );
}

describe("ProcessNumberField", () => {
  it("aplica a máscara enquanto digita e guarda só dígitos", async () => {
    const user = userEvent.setup();
    const onValidate = vi.fn().mockResolvedValue(validation({}));
    render(<Harness onValidate={onValidate} />);

    const input = screen.getByLabelText("Número do processo");
    await user.type(input, "07007001820258260100");

    expect(input).toHaveValue("0700700-18.2025.8.26.0100");
  });

  it("valida em tempo real ao completar 20 dígitos e sugere o tribunal", async () => {
    const user = userEvent.setup();
    const onValidate = vi.fn().mockResolvedValue(
      validation({
        valid: true,
        inferred_court: { id: 60, code: "TJSP", name: "Tribunal de Justiça de São Paulo" },
      }),
    );
    const onCourtInferred = vi.fn();
    render(<Harness onValidate={onValidate} onCourtInferred={onCourtInferred} />);

    await user.type(screen.getByLabelText("Número do processo"), "07007001820258260100");

    await waitFor(() => expect(onValidate).toHaveBeenCalledWith("07007001820258260100"));
    expect(await screen.findByText(/Tribunal sugerido: TJSP/)).toBeInTheDocument();
    expect(onCourtInferred).toHaveBeenCalledWith({
      id: "60",
      code: "TJSP",
      name: "Tribunal de Justiça de São Paulo",
    });
  });

  it("mostra o erro do backend para dígito verificador inválido", async () => {
    const user = userEvent.setup();
    const onValidate = vi.fn().mockResolvedValue(
      validation({
        valid: false,
        error: "Dígito verificador não confere: informado 77, esperado 76.",
      }),
    );
    render(<Harness onValidate={onValidate} />);

    await user.type(screen.getByLabelText("Número do processo"), "00001237720251000001");

    expect(await screen.findByRole("alert")).toHaveTextContent("Dígito verificador não confere");
  });

  it("não valida antes de completar 20 dígitos", async () => {
    const user = userEvent.setup();
    const onValidate = vi.fn().mockResolvedValue(validation({}));
    render(<Harness onValidate={onValidate} />);

    await user.type(screen.getByLabelText("Número do processo"), "0700700");

    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(onValidate).not.toHaveBeenCalled();
  });
});

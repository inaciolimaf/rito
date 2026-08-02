import { MoneyField } from "@/components/domain/MoneyField";
import { formatBrl, formatDecimalPtBr, digitsToDecimalRaw } from "@/lib/money";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";

interface FormValues {
  amount: string;
}

function Harness({ initial = "" }: { initial?: string }): JSX.Element {
  const form = useForm<FormValues>({ defaultValues: { amount: initial } });
  return (
    <form onSubmit={form.handleSubmit(() => undefined)}>
      <MoneyField control={form.control} name="amount" label="Valor da causa" />
      <output data-testid="raw">{form.watch("amount")}</output>
    </form>
  );
}

describe("lib/money", () => {
  it("converte dígitos em valor cru e formata pt-BR — ida e volta", () => {
    expect(digitsToDecimalRaw("123456")).toBe("1234.56");
    expect(digitsToDecimalRaw("")).toBe("");
    expect(formatDecimalPtBr("1234.56")).toBe("1.234,56");
    expect(formatDecimalPtBr("999999999999.99")).toBe("999.999.999.999,99");
    expect(formatDecimalPtBr("")).toBe("");
  });

  it("formata moeda brasileira para cards", () => {
    // Intl usa espaço não-quebrável entre "R$" e o valor — normalizar para comparar.
    const normalize = (value: string): string => value.replace(/[\u00a0]/g, " ");
    expect(normalize(formatBrl(1234.56))).toBe("R$ 1.234,56");
    expect(normalize(formatBrl(0))).toBe("R$ 0,00");
    expect(formatBrl(null)).toBe("—");
  });
});

describe("MoneyField", () => {
  it("digita centavos, mostra máscara pt-BR e guarda valor cru com ponto", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const input = screen.getByLabelText("Valor da causa");
    await user.type(input, "123456");

    expect(input).toHaveValue("1.234,56");
    expect(screen.getByTestId("raw")).toHaveTextContent("1234.56");
  });

  it("apagar volta o campo ao vazio", async () => {
    const user = userEvent.setup();
    render(<Harness initial="10.00" />);

    const input = screen.getByLabelText("Valor da causa");
    expect(input).toHaveValue("10,00");

    await user.clear(input);
    expect(input).toHaveValue("");
    expect(screen.getByTestId("raw")).toHaveTextContent(/^$/);
  });
});

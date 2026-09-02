import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";

import { PercentField } from "@/components/domain/PercentField";
import { parseMoneyInput, parsePercentInput } from "@/lib/money";

interface FormValues {
  rate: string;
}

function Harness({ initial = "" }: { initial?: string }): JSX.Element {
  const form = useForm<FormValues>({ defaultValues: { rate: initial } });
  return (
    <form onSubmit={form.handleSubmit(() => undefined)}>
      <PercentField control={form.control} name="rate" label="Honorários" />
      <output data-testid="raw">{form.watch("rate")}</output>
    </form>
  );
}

/** A casca (label + Controller + máscara pt-BR) é a mesma para dinheiro e percentual desde
 * a spec 119; o que distingue os dois é só o parsing do que foi digitado. */
describe("máscara decimal compartilhada", () => {
  it("dinheiro corta em 14 dígitos e trata o digitado como centavos", () => {
    expect(parseMoneyInput("123456")).toBe("1234.56");
    expect(parseMoneyInput("R$ 1.234,56")).toBe("1234.56");
    expect(parseMoneyInput("")).toBe("");
    expect(parseMoneyInput("9".repeat(20))).toBe("999999999999.99");
  });

  it("percentual limita em 100,00", () => {
    expect(parsePercentInput("1050")).toBe("10.50");
    expect(parsePercentInput("99999")).toBe("100.00");
    expect(parsePercentInput("")).toBe("");
  });

  it("o campo exibe com vírgula e guarda o valor cru com ponto", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const input = screen.getByLabelText("Honorários");
    await user.type(input, "1050");

    expect(input).toHaveValue("10,50");
    expect(screen.getByTestId("raw")).toHaveTextContent("10.50");
  });
});

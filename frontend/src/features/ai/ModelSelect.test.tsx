import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ModelSelect } from "@/features/ai/ModelSelect";
import { formatPricePerMillion } from "@/features/ai/pricing";
import type { ModelInfoData } from "@/features/ai/api";

const MODELS: ModelInfoData[] = [
  {
    id: "fabricante-x/modelo-y",
    name: "Modelo Y",
    context_length: 128000,
    prompt_price_usd: 0.0000015,
    completion_price_usd: 0.000006,
  },
  {
    id: "fabricante-z/modelo-w",
    name: "Modelo W",
    context_length: 32000,
    prompt_price_usd: 0.0000005,
    completion_price_usd: 0.0000015,
  },
];

describe("ModelSelect", () => {
  it("mostra preço e contexto de cada modelo na hora de escolher (spec 081 §7)", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ModelSelect
        id="model-copilot"
        label="Modelo"
        models={MODELS}
        value="fabricante-x/modelo-y"
        onChange={onChange}
      />,
    );

    const option = screen.getByRole("option", { name: /Modelo Y/ });
    // Preço do OpenRouter é por token; a UI mostra por milhão, que é como se compara.
    expect(option).toHaveTextContent("entrada US$ 1.50/1M");
    expect(option).toHaveTextContent("saída US$ 6.00/1M");
    expect(option).toHaveTextContent("128k de contexto");

    await user.selectOptions(screen.getByLabelText("Modelo"), "fabricante-z/modelo-w");
    expect(onChange).toHaveBeenCalledWith("fabricante-z/modelo-w");
  });

  it("modelo configurado fora do catálogo continua selecionável", () => {
    render(
      <ModelSelect
        id="model-copilot"
        label="Modelo"
        models={MODELS}
        value="fabricante-antigo/descontinuado"
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByRole("option", { name: /fora do catálogo/ })).toBeInTheDocument();
  });

  it("converte preço por token em preço por milhão", () => {
    expect(formatPricePerMillion(0.0000015)).toBe("US$ 1.50/1M");
    expect(formatPricePerMillion(0)).toBe("US$ 0.00/1M");
  });
});

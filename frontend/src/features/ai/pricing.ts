import type { ModelInfoData } from "@/features/ai/api";

/** Preço do OpenRouter é por token; ninguém raciocina nessa escala — a UI mostra por
 * milhão, que é como os provedores anunciam e como se comparam dois modelos. */
export function formatPricePerMillion(pricePerToken: number): string {
  const perMillion = pricePerToken * 1_000_000;
  const digits = perMillion >= 100 ? 0 : 2;
  return `US$ ${perMillion.toFixed(digits)}/1M`;
}

export function formatContextLength(tokens: number): string {
  if (tokens <= 0) return "contexto desconhecido";
  return `${Math.round(tokens / 1000)}k de contexto`;
}

export function describeModel(model: ModelInfoData): string {
  return [
    model.name,
    `entrada ${formatPricePerMillion(model.prompt_price_usd)}`,
    `saída ${formatPricePerMillion(model.completion_price_usd)}`,
    formatContextLength(model.context_length),
  ].join(" · ");
}

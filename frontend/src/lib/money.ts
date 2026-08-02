// Máscara e formatação de dinheiro/percentual (spec 024, regra 1): a UI usa vírgula
// decimal pt-BR; o valor cru que vai para o formulário/API usa ponto ("1234.56").
// Compartilhado por MoneyField/PercentField (components/domain) e pelo painel financeiro
// — todo o módulo financeiro (specs 054+) bebe daqui.

const ptBrFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const brlFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});

/** Dígitos crus (como digitados, sempre tratados como centavos) → valor cru com ponto.
 * "123456" → "1234.56" · "" → "" */
export function digitsToDecimalRaw(digits: string): string {
  if (digits === "") return "";
  const cents = parseInt(digits, 10);
  return (cents / 100).toFixed(2);
}

/** Valor cru com ponto → exibição pt-BR. "1234.56" → "1.234,56" · "" → "" */
export function formatDecimalPtBr(raw: string): string {
  if (raw === "") return "";
  return ptBrFormatter.format(Number(raw));
}

/** Número da API (ou null) → moeda brasileira para cards. 1234.56 → "R$ 1.234,56" */
export function formatBrl(value: number | null): string {
  return value === null ? "—" : brlFormatter.format(value);
}

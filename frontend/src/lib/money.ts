// Máscara e formatação de dinheiro/percentual (spec 024, regra 1): a UI usa vírgula
// decimal pt-BR; o valor cru que vai para o formulário/API usa ponto ("1234.56").
// Compartilhado por MoneyField/PercentField (components/domain) e pelo painel financeiro
// — todo o módulo financeiro (specs 054+) bebe daqui.

import { stripNonDigits } from "@/lib/br-masks";

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

/** Texto digitado no campo de dinheiro → valor cru. 14 dígitos = NUMERIC(14,2) contando
 * os 2 de centavos (spec 024, regra 1). "R$ 1.234,56" → "1234.56" */
export function parseMoneyInput(typed: string): string {
  return digitsToDecimalRaw(stripNonDigits(typed).slice(0, 14));
}

/** Texto digitado no campo de percentual → valor cru, com teto de 100,00 na máscara
 * (spec 024, regra 2). O backend é quem valida de fato (422). "1050" → "10.50" */
export function parsePercentInput(typed: string): string {
  const digits = stripNonDigits(typed).slice(0, 5);
  const cents = digits === "" ? 0 : Math.min(parseInt(digits, 10), 10000);
  return digits === "" ? "" : (cents / 100).toFixed(2);
}

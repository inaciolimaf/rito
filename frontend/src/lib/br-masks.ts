// Máscara é só UX (spec 018, regra 3) — o dígito verificador de CPF/CNPJ e as demais
// validações reais moram só no backend (app/core/br_documents.py); aqui a gente só
// formata/limita dígitos para exibição, o 422 do servidor é quem valida de fato (mesmo
// precedente da spec 011, ver features/account/schema.ts).

export function stripNonDigits(value: string): string {
  return value.replace(/\D/g, "");
}

export function formatCpf(digits: string): string {
  const d = digits.slice(0, 11);
  const parts = [d.slice(0, 3), d.slice(3, 6), d.slice(6, 9)].filter(Boolean);
  let result = parts.join(".");
  if (d.length > 9) result += `-${d.slice(9, 11)}`;
  return result;
}

export function formatCnpj(digits: string): string {
  const d = digits.slice(0, 14);
  let result = d.slice(0, 2);
  if (d.length > 2) result += `.${d.slice(2, 5)}`;
  if (d.length > 5) result += `.${d.slice(5, 8)}`;
  if (d.length > 8) result += `/${d.slice(8, 12)}`;
  if (d.length > 12) result += `-${d.slice(12, 14)}`;
  return result;
}

export function formatCpfOrCnpj(digits: string, personType: "PF" | "PJ"): string {
  return personType === "PJ" ? formatCnpj(digits) : formatCpf(digits);
}

export function maxDigitsFor(personType: "PF" | "PJ"): number {
  return personType === "PJ" ? 14 : 11;
}

export function formatPhone(digits: string): string {
  const d = digits.slice(0, 11);
  if (d.length <= 2) return d;
  const ddd = d.slice(0, 2);
  const rest = d.slice(2);
  // Celular (11 dígitos) tem 5 dígitos antes do traço; fixo (10) tem 4.
  const splitAt = d.length > 10 ? 5 : 4;
  const first = rest.slice(0, splitAt);
  const second = rest.slice(splitAt);
  return second ? `(${ddd}) ${first}-${second}` : `(${ddd}) ${first}`;
}

export function formatPostalCode(digits: string): string {
  const d = digits.slice(0, 8);
  return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d;
}

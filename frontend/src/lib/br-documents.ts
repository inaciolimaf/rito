// Espelho em TypeScript de `backend/app/core/br_documents.py` (spec 011, regra 1).
//
// Spec 138, regra 7: onde o formulário JÁ valida o documento, ele precisa validar o
// MESMO que o backend valida. Validar só o comprimento e deixar o dígito verificador
// para o 422 é pior que não validar nada — o usuário lê "11 dígitos", digita 11 dígitos,
// passa no formulário e toma um erro do servidor que contradiz o que a tela acabou de
// dizer. Nenhuma regra nova é inventada aqui: é o algoritmo de lá, linha a linha.

export function stripDocumentMask(value: string): string {
  return value.replace(/\D/g, "");
}

function checkDigit(digits: string, weights: number[]): number {
  const total = weights.reduce((sum, weight, index) => sum + Number(digits[index]) * weight, 0);
  const remainder = total % 11;
  return remainder < 2 ? 0 : 11 - remainder;
}

const CPF_FIRST_WEIGHTS = [10, 9, 8, 7, 6, 5, 4, 3, 2];
const CPF_SECOND_WEIGHTS = [11, 10, 9, 8, 7, 6, 5, 4, 3, 2];
const CNPJ_FIRST_WEIGHTS = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
const CNPJ_SECOND_WEIGHTS = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];

export function isValidCpf(value: string): boolean {
  const digits = stripDocumentMask(value);
  if (digits.length !== 11 || digits === digits[0]?.repeat(11)) return false;
  const first = checkDigit(digits.slice(0, 9), CPF_FIRST_WEIGHTS);
  const second = checkDigit(`${digits.slice(0, 9)}${first}`, CPF_SECOND_WEIGHTS);
  return digits.slice(9) === `${first}${second}`;
}

export function isValidCnpj(value: string): boolean {
  const digits = stripDocumentMask(value);
  if (digits.length !== 14 || digits === digits[0]?.repeat(14)) return false;
  const first = checkDigit(digits.slice(0, 12), CNPJ_FIRST_WEIGHTS);
  const second = checkDigit(`${digits.slice(0, 12)}${first}`, CNPJ_SECOND_WEIGHTS);
  return digits.slice(12) === `${first}${second}`;
}

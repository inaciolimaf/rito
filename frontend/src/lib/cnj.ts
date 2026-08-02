// Máscara do número único do processo (CNJ — spec 025, regra 9: armazenado só com
// dígitos, a máscara é sempre de apresentação). A validação real (DV, ano, segmento)
// mora só no backend (app/domain/lawsuits/cnj.py) — aqui é só formatação.

export function formatCnj(digits: string): string {
  const d = digits.slice(0, 20);
  let result = d.slice(0, 7);
  if (d.length > 7) result += `-${d.slice(7, 9)}`;
  if (d.length > 9) result += `.${d.slice(9, 13)}`;
  if (d.length > 13) result += `.${d.slice(13, 14)}`;
  if (d.length > 14) result += `.${d.slice(14, 16)}`;
  if (d.length > 16) result += `.${d.slice(16, 20)}`;
  return result;
}

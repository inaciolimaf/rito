// Espelha app/domain/financial/service.py::_split_amount/_installment_due_dates (spec 057,
// regras 2/6) — só pra o preview ao vivo no formulário; a fonte de verdade da divisão real
// continua sendo o backend (o cliente nunca decide o valor gravado).

function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

/** Divide `total` em `count` parcelas de 2 casas, com o resto de arredondamento inteiro
 * na última parcela — a soma bate sempre. 100 ÷ 3 = 33.33 + 33.33 + 33.34. */
export function splitInstallmentAmounts(total: number, count: number): number[] {
  const share = Math.round((total / count) * 100) / 100;
  const shares = new Array<number>(count).fill(share);
  const remainder = Math.round((total - share * count) * 100) / 100;
  if (remainder !== 0) {
    shares[count - 1] = Math.round((share + remainder) * 100) / 100;
  }
  return shares;
}

/** Vencimento mensal a partir de `baseDueDate` ("AAAA-MM-DD"); dia 31 num mês curto usa
 * o último dia do mês — o dia sempre vem da ÂNCORA (primeira data), nunca da parcela
 * anterior já clampada. */
export function installmentDueDates(baseDueDate: string, count: number): string[] {
  const parts = baseDueDate.split("-").map(Number);
  const year = parts[0] ?? 1970;
  const month = parts[1] ?? 1;
  const day = parts[2] ?? 1;
  const dates = [baseDueDate];
  let currentYear = year;
  let currentMonth = month;
  for (let i = 1; i < count; i++) {
    currentMonth += 1;
    if (currentMonth > 12) {
      currentMonth = 1;
      currentYear += 1;
    }
    const clampedDay = Math.min(day, daysInMonth(currentYear, currentMonth));
    dates.push(
      `${currentYear}-${String(currentMonth).padStart(2, "0")}-${String(clampedDay).padStart(2, "0")}`,
    );
  }
  return dates;
}

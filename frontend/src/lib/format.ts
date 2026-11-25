// Formatação pt-BR de data e número (CLAUDE.md §9: data `DD/MM/AAAA`, decimal com
// vírgula). `lib/money.ts` continua sendo a casa da máscara de dinheiro e do `R$`; aqui
// moram as duas conversões genéricas que sete features tinham reescrito à mão.
//
// Spec 138, regra 10: a conversão ISO → DD/MM/AAAA estava copiada em sete arquivos e o
// `toFixed()` imprimia ponto decimal em oito — a regra dos 3 usos foi estourada nas duas.

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

/** Data-only ISO (`AAAA-MM-DD`) → `DD/MM/AAAA`. `null`/vazio → `—`.
 *
 * Fatiar a string em vez de passar por `new Date()` é deliberado: `new Date("2026-03-01")`
 * é interpretado como meia-noite UTC e, num fuso a oeste, `toLocaleDateString` devolve o
 * dia anterior. Aceita também um datetime ISO — nesse caso usa só a parte da data, que é
 * o que o campo significa. */
export function formatBrDate(value: string | null | undefined): string {
  if (!value) return "—";
  const [datePart] = value.split("T");
  const [year, month, day] = (datePart ?? "").split("-");
  if (!year || !month || !day) return "—";
  return `${day}/${month}/${year}`;
}

/** Instante ISO com fuso (`created_at` e amigos) → `DD/MM/AAAA HH:MM` no fuso do
 * navegador. Aqui `new Date()` é o certo: o valor É um instante, não uma data de
 * calendário. */
export function formatBrDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  return dateTimeFormatter.format(parsed);
}

/** Número → pt-BR com casas fixas. `12.5` → `"12,5"` (1 casa) · `1500.5` → `"1.500,50"`. */
export function formatNumberPtBr(value: number, fractionDigits = 2): string {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value);
}

/** Dólar do custo de IA na convenção brasileira: `US$ 1.500,50`. O valor é cobrado em
 * dólar pelo OpenRouter, mas quem lê a tela lê em português — e uma chamada custa
 * frações de centavo, daí as casas configuráveis. */
export function formatUsd(value: number, fractionDigits = 2): string {
  return `US$ ${formatNumberPtBr(value, fractionDigits)}`;
}

/** Bytes → `12,5 GB`, uma casa decimal, vírgula. */
export function formatGb(bytes: number): string {
  return `${formatNumberPtBr(bytes / 1024 ** 3, 1)} GB`;
}

import { describe, expect, it } from "vitest";

import { shiftAnchor, viewRange } from "@/features/schedule/calendar";

/** Mês da âncora, 1-based, para ler as asserções sem contar de 0. */
function mes(data: Date): number {
  return data.getMonth() + 1;
}

describe("shiftAnchor no mês", () => {
  it("não pula um mês quando a âncora é dia 31 e o destino tem 30 dias", () => {
    // Bug encontrado em 31/08/2026 pela jornada e2e 6/25: `setMonth()` preserva o dia,
    // então 31/08 + 1 mês virava 01/10 — setembro inteiro ficava inalcançável para
    // quem clicasse "Próximo" no dia 31.
    const trintaEUmDeAgosto = new Date(2026, 7, 31);

    const proximo = shiftAnchor("month", trintaEUmDeAgosto, 1);

    expect(mes(proximo)).toBe(9);
    expect(proximo.getFullYear()).toBe(2026);
  });

  it("também não pula para trás", () => {
    // 31/03 - 1 mês cairia em 02/03 ou 03/03 (fevereiro é mais curto ainda).
    const trintaEUmDeMarco = new Date(2026, 2, 31);

    const anterior = shiftAnchor("month", trintaEUmDeMarco, -1);

    expect(mes(anterior)).toBe(2);
    expect(anterior.getFullYear()).toBe(2026);
  });

  it("atravessa a virada do ano nos dois sentidos", () => {
    expect(mes(shiftAnchor("month", new Date(2026, 11, 31), 1))).toBe(1);
    expect(shiftAnchor("month", new Date(2026, 11, 31), 1).getFullYear()).toBe(2027);
    expect(mes(shiftAnchor("month", new Date(2026, 0, 31), -1))).toBe(12);
    expect(shiftAnchor("month", new Date(2026, 0, 31), -1).getFullYear()).toBe(2025);
  });

  it("a grade pedida à API é a do mês de destino, não a de um mês pulado", () => {
    const proximo = shiftAnchor("month", new Date(2026, 7, 31), 1);

    const { from, to } = viewRange("month", proximo);

    // A grade de setembro/2026 começa em 30/08 (domingo) e termina em 10/10.
    expect(from).toBe("2026-08-30");
    expect(to).toBe("2026-10-10");
  });

  it("visões de dia e semana continuam andando por dias, não por mês", () => {
    const base = new Date(2026, 7, 31);

    expect(shiftAnchor("day", base, 1).getDate()).toBe(1);
    expect(mes(shiftAnchor("day", base, 1))).toBe(9);
    expect(shiftAnchor("week", base, 1).getDate()).toBe(7);
    expect(mes(shiftAnchor("week", base, 1))).toBe(9);
  });
});

import { describe, expect, it } from "vitest";

import {
  formatBrDate,
  formatBrDateTime,
  formatGb,
  formatNumberPtBr,
  formatUsd,
} from "@/lib/format";

describe("formatBrDate (CLAUDE.md §9)", () => {
  it("converte ISO data-only em DD/MM/AAAA", () => {
    expect(formatBrDate("2026-03-01")).toBe("01/03/2026");
  });

  it("não anda um dia para trás em fuso a oeste — não passa por new Date()", () => {
    // `new Date("2026-01-01")` é meia-noite UTC; `toLocaleDateString` em GMT-3 daria 31/12.
    expect(formatBrDate("2026-01-01")).toBe("01/01/2026");
  });

  it("aceita datetime e usa só a data", () => {
    expect(formatBrDate("2026-03-01T23:30:00Z")).toBe("01/03/2026");
  });

  it("nulo e vazio viram travessão", () => {
    expect(formatBrDate(null)).toBe("—");
    expect(formatBrDate("")).toBe("—");
    expect(formatBrDateTime(null)).toBe("—");
  });
});

describe("números em pt-BR", () => {
  it("usa vírgula decimal e separador de milhar", () => {
    expect(formatNumberPtBr(1234.5, 2)).toBe("1.234,50");
    expect(formatNumberPtBr(12.5, 1)).toBe("12,5");
  });

  it("dólar de IA e armazenamento seguem a mesma convenção", () => {
    expect(formatUsd(1500.5)).toBe("US$ 1.500,50");
    expect(formatUsd(0.0012, 4)).toBe("US$ 0,0012");
    expect(formatGb(1024 ** 3 * 12.5)).toBe("12,5 GB");
  });
});

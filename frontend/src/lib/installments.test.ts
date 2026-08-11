import { describe, expect, it } from "vitest";

import { installmentDueDates, splitInstallmentAmounts } from "@/lib/installments";

describe("splitInstallmentAmounts", () => {
  it("100 dividido por 3 dá 33.33 + 33.33 + 33.34", () => {
    expect(splitInstallmentAmounts(100, 3)).toEqual([33.33, 33.33, 33.34]);
  });
});

describe("installmentDueDates", () => {
  it("dia 31 em fevereiro usa o último dia do mês", () => {
    expect(installmentDueDates("2026-01-31", 3)).toEqual([
      "2026-01-31",
      "2026-02-28",
      "2026-03-31",
    ]);
  });
});

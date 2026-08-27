import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDebounced } from "@/features/search/useDebounced";

describe("useDebounced", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("segura o valor por 250 ms (spec 096, regra 7)", () => {
    const { result, rerender } = renderHook(({ value }) => useDebounced(value), {
      initialProps: { value: "m" },
    });

    rerender({ value: "mar" });
    expect(result.current).toBe("m");

    act(() => void vi.advanceTimersByTime(249));
    expect(result.current).toBe("m");

    act(() => void vi.advanceTimersByTime(1));
    expect(result.current).toBe("mar");
  });

  it("digitação contínua reinicia a espera — só o último valor chega", () => {
    const { result, rerender } = renderHook(({ value }) => useDebounced(value), {
      initialProps: { value: "" },
    });

    for (const parcial of ["m", "ma", "mar", "mari"]) {
      rerender({ value: parcial });
      act(() => void vi.advanceTimersByTime(200));
    }
    expect(result.current).toBe("");

    act(() => void vi.advanceTimersByTime(250));
    expect(result.current).toBe("mari");
  });
});

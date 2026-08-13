import { renderHook } from "@testing-library/react";
import { waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useAutosave } from "@/components/domain/useAutosave";

describe("useAutosave", () => {
  it("não salva na transição inicial de enabled=false para true (carregamento)", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(
      ({ value, enabled }: { value: string; enabled: boolean }) =>
        useAutosave(value, save, { delayMs: 10, enabled }),
      { initialProps: { value: "carregado", enabled: false } },
    );

    rerender({ value: "carregado", enabled: true });

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(save).not.toHaveBeenCalled();
  });

  it("dispara só depois do debounce, com o último valor (regra 2, spec 065)", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderHook(
      ({ value }: { value: string }) => useAutosave(value, save, { delayMs: 30, enabled: true }),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "ab" });
    rerender({ value: "abc" });

    expect(save).not.toHaveBeenCalled();

    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith("abc");
  });

  it("reporta erro sem travar o próximo autosave (regra 3)", async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error("falhou")).mockResolvedValue(undefined);
    const { result, rerender } = renderHook(
      ({ value }: { value: string }) => useAutosave(value, save, { delayMs: 10, enabled: true }),
      { initialProps: { value: "a" } },
    );

    rerender({ value: "b" });
    await waitFor(() => expect(result.current).toBe("error"));

    rerender({ value: "c" });
    await waitFor(() => expect(result.current).toBe("saved"));
    expect(save).toHaveBeenCalledTimes(2);
  });
});

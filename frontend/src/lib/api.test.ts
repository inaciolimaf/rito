import { describe, expect, it } from "vitest";

import { apiRequest, getRefreshToken, setSession } from "@/lib/api";
import { getRefreshCallCount } from "@/mocks/handlers";

interface MeBody {
  id: string;
}

describe("apiRequest", () => {
  it("401 dispara refresh e reexecuta a requisição original", async () => {
    setSession({ accessToken: "token-expirado", refreshToken: "refresh-token-1" });

    const me = await apiRequest<MeBody>("/api/v1/auth/me");

    expect(me.id).toBeTruthy();
    expect(getRefreshCallCount()).toBe(1);
  });

  it("refresh falho limpa a sessão", async () => {
    setSession({ accessToken: "token-invalido", refreshToken: "refresh-token-invalido" });

    await expect(apiRequest("/api/v1/auth/me")).rejects.toThrow();

    expect(getRefreshToken()).toBeNull();
  });

  it("requisições concorrentes fazem 1 refresh só", async () => {
    setSession({ accessToken: "token-expirado", refreshToken: "refresh-token-1" });

    const [first, second] = await Promise.all([
      apiRequest<MeBody>("/api/v1/auth/me"),
      apiRequest<MeBody>("/api/v1/auth/me"),
    ]);

    expect(first.id).toBeTruthy();
    expect(second.id).toBeTruthy();
    expect(getRefreshCallCount()).toBe(1);
  });
});

import { describe, expect, it } from "vitest";

import { ApiError, toApiError } from "@/lib/errors";

describe("toApiError", () => {
  it("converte problem+json em ApiError tipado", async () => {
    const response = new Response(
      JSON.stringify({
        type: "https://rito.app/errors/validation",
        title: "Dados inválidos",
        status: 422,
        detail: "Um ou mais campos são inválidos.",
        instance: "/api/v1/auth/reset-password",
        errors: [{ loc: ["password"], msg: "Mínimo de 8 caracteres." }],
      }),
      { status: 422 },
    );

    const error = await toApiError(response, "/api/v1/auth/reset-password");

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(422);
    expect(error.title).toBe("Dados inválidos");
    expect(error.message).toBe("Um ou mais campos são inválidos.");
    expect(error.errors).toHaveLength(1);
  });

  it("cai num ApiError genérico se o corpo não for problem+json", async () => {
    const response = new Response("não é json", { status: 500 });

    const error = await toApiError(response, "/api/v1/health");

    expect(error.status).toBe(500);
    expect(error.title).toBe("Erro");
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntegrationAlertBanner } from "@/components/domain/IntegrationAlertBanner";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

const mockUseAuth = vi.fn();
vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => mockUseAuth(),
}));

function renderBanner(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <IntegrationAlertBanner />
    </QueryClientProvider>,
  );
}

describe("IntegrationAlertBanner", () => {
  afterEach(() => {
    server.resetHandlers();
    cleanup();
  });

  it("só aparece para ADMINISTRADOR/GESTOR — Colaborador não vê (regra 4)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/integration-alerts`, () =>
        HttpResponse.json({
          items: [
            {
              id: "alert-1",
              integration: "datajud",
              severity: "critical",
              code: "api_key_rotated",
              message: "A chave pública do DataJud foi rotacionada.",
              responsible_user_id: null,
              resolved_at: null,
              resolved_by: null,
              created_at: "2026-08-11T10:00:00Z",
            },
          ],
          total: 1,
        }),
      ),
    );

    mockUseAuth.mockReturnValue({ user: { id: "colaborador-1", role: "COLABORADOR" } });
    renderBanner();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    cleanup();

    mockUseAuth.mockReturnValue({ user: { id: "gestor-1", role: "GESTOR" } });
    renderBanner();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("A chave pública do DataJud foi rotacionada.")).toBeInTheDocument();
  });
});

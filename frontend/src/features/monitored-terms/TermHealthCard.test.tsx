import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";
import { TermHealthCard } from "@/features/monitored-terms/TermHealthCard";

function renderCard(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <TermHealthCard termId="term-1" />
    </QueryClientProvider>,
  );
}

describe("TermHealthCard", () => {
  afterEach(() => server.resetHandlers());

  it("mostra status, falhas seguidas e as datas da última/próxima sincronização (spec 049 §6)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/monitored-terms/term-1/health`, () =>
        HttpResponse.json({
          id: "term-1",
          status: "FALHA",
          consecutive_failures: 2,
          last_sync_at: "2026-08-11T08:00:00Z",
          last_success_at: "2026-08-09T08:00:00Z",
          next_sync_at: "2026-08-12T03:17:00Z",
          alert_id: "alert-1",
        }),
      ),
    );

    renderCard();

    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getByTestId("term-status-badge")).toHaveTextContent("Falha");
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TimesheetReport } from "@/features/reports/TimesheetReport";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1", role: "ADMINISTRADOR" } }),
}));

function renderReport(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <TimesheetReport />
    </QueryClientProvider>,
  );
}

describe("TimesheetReport", () => {
  afterEach(() => server.resetHandlers());

  it("dia sem acesso fica vazio; dia com acesso mostra o desvio (spec 073 §6-7)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/reports/timesheet`, () =>
        HttpResponse.json({
          user_id: "u1",
          month: "2026-08-01",
          days: [
            {
              day: "2026-08-01",
              first_access: "2026-08-01T12:30:00Z",
              last_access: "2026-08-01T20:00:00Z",
              access_count: 2,
              deviation_minutes: 30,
              is_weekend: false,
              is_holiday: false,
            },
            {
              day: "2026-08-02",
              first_access: null,
              last_access: null,
              access_count: 0,
              deviation_minutes: null,
              is_weekend: true,
              is_holiday: false,
            },
          ],
        }),
      ),
    );

    renderReport();

    expect(await screen.findByText("+30 min")).toBeInTheDocument();
    expect(screen.getByText("fim de semana")).toBeInTheDocument();
  });
});

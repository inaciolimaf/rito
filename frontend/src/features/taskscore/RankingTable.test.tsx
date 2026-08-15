import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { RankingTable } from "@/features/taskscore/RankingTable";
import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";

function renderTable(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RankingTable />
    </QueryClientProvider>,
  );
}

describe("RankingTable", () => {
  afterEach(() => server.resetHandlers());

  it("oferece os 4 critérios de ordenação (spec 039 regra 4 / spec 071 §8)", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/taskscore/ranking`, ({ request }) => {
        const sort = new URL(request.url).searchParams.get("sort");
        return HttpResponse.json({
          period: "2026-08",
          sort,
          items: [
            {
              user_id: "u1",
              user_name: "Ana Advogada",
              points: 80,
              tasks_completed: 10,
              on_time: 9,
              late: 1,
              assigned: 12,
              engagement: 0.833,
              points_goal: 100,
              goal_pct: 80.0,
            },
          ],
        });
      }),
    );

    renderTable();

    expect(await screen.findByText("Ana Advogada")).toBeInTheDocument();

    const select = screen.getByLabelText("Classificar por");
    const options = Array.from(select.querySelectorAll("option")).map((option) => option.value);
    expect(options).toEqual(["points", "volume", "late", "engagement"]);

    await userEvent.selectOptions(select, "late");
    expect(await screen.findByText("Ana Advogada")).toBeInTheDocument();
  });
});

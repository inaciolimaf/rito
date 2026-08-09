import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ScheduleEvent } from "@/features/schedule/api";
import { CalendarPage } from "@/features/schedule/CalendarPage";
import { formatIsoDay } from "@/features/schedule/calendar";

const { mockListSchedule, mockListUsers, mockNewTaskModal } = vi.hoisted(() => ({
  mockListSchedule: vi.fn(),
  mockListUsers: vi.fn(),
  mockNewTaskModal: vi.fn((props: { open: boolean; initialDate: string | null }) =>
    props.open ? <div data-testid="new-task-modal">data={props.initialDate}</div> : null,
  ),
}));

vi.mock("@/features/schedule/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/features/schedule/api")>();
  return {
    ...original,
    listSchedule: mockListSchedule,
    getIcalStatus: vi.fn().mockResolvedValue({ enabled: false, url: null }),
  };
});

vi.mock("@/features/users/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/features/users/api")>();
  return { ...original, listUsers: mockListUsers };
});

vi.mock("@/features/posts/NewTaskModal", () => ({
  NewTaskModal: (props: { open: boolean; initialDate: string | null }) => mockNewTaskModal(props),
}));

function makeEvent(overrides: Partial<ScheduleEvent>): ScheduleEvent {
  return {
    post_id: "p1",
    lawsuit_id: "l1",
    task_type_name: "CONTESTAÇÃO SIMPLES",
    date: formatIsoDay(new Date()),
    scheduled_date: formatIsoDay(new Date()),
    scheduled_time: "14:30:00",
    end_date: null,
    end_time: null,
    deadline_date: null,
    all_day: false,
    location: null,
    status: "PENDENTE",
    is_urgent: false,
    is_important: false,
    assignee_names: ["Usuário de Teste"],
    ...overrides,
  };
}

function renderPage(): ReturnType<typeof render> {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CalendarPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CalendarPage (spec 037)", () => {
  beforeEach(() => {
    mockListSchedule.mockResolvedValue([]);
    mockListUsers.mockResolvedValue({ items: [], next_cursor: null, total: 0 });
    mockNewTaskModal.mockClear();
  });

  it("navega entre as 4 visões", async () => {
    renderPage();
    expect(await screen.findByTestId("month-view")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("view-week"));
    expect(await screen.findByTestId("week-view")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("view-day"));
    expect(await screen.findByTestId("day-view")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("view-agenda"));
    expect(await screen.findByTestId("agenda-view")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("view-month"));
    expect(await screen.findByTestId("month-view")).toBeInTheDocument();
  });

  it("mostra os chips com a cor de cada status (regra 3)", async () => {
    mockListSchedule.mockResolvedValue([
      makeEvent({ post_id: "p1", status: "PENDENTE", task_type_name: "PENDENTE UMA" }),
      makeEvent({ post_id: "p2", status: "CONCLUIDA", task_type_name: "CONCLUIDA DUAS" }),
      makeEvent({ post_id: "p3", status: "ATRASADA", task_type_name: "ATRASADA TRÊS" }),
    ]);
    renderPage();

    await waitFor(() => expect(screen.getAllByTestId("schedule-event")).toHaveLength(3));
    const byStatus = new Map(
      screen
        .getAllByTestId("schedule-event")
        .map((chip) => [chip.getAttribute("data-status"), chip.textContent]),
    );
    expect(byStatus.get("PENDENTE")).toContain("PENDENTE UMA");
    expect(byStatus.get("CONCLUIDA")).toContain("CONCLUIDA DUAS");
    expect(byStatus.get("ATRASADA")).toContain("ATRASADA TRÊS");
  });

  it("clicar num dia abre o formulário com a data pré-preenchida (regra 7)", async () => {
    renderPage();
    expect(await screen.findByTestId("month-view")).toBeInTheDocument();

    const today = formatIsoDay(new Date());
    await userEvent.click(screen.getByTestId(`day-cell-${today}`));

    expect(await screen.findByTestId("new-task-modal")).toHaveTextContent(`data=${today}`);
  });

  it("navegar para o próximo mês muda o intervalo pedido à API", async () => {
    renderPage();
    expect(await screen.findByTestId("month-view")).toBeInTheDocument();
    await waitFor(() => expect(mockListSchedule).toHaveBeenCalled());
    const firstCall = mockListSchedule.mock.calls[0] as unknown as [{ from: string }];
    const firstRange = firstCall[0].from;

    await userEvent.click(screen.getByRole("button", { name: "Próximo →" }));

    await waitFor(() => {
      const calls = mockListSchedule.mock.calls as unknown as [{ from: string }][];
      const ranges = calls.map((call) => call[0].from);
      expect(ranges.some((from) => from > firstRange)).toBe(true);
    });
  });
});

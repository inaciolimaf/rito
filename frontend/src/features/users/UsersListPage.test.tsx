import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BASE_URL } from "@/mocks/handlers";
import { server } from "@/test/msw-server";
import { UsersListPage } from "@/features/users/UsersListPage";

vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "admin-1", role: "GESTOR" } }),
}));

const ALL_USERS = [
  {
    id: "1",
    email: "gestor@example.com",
    name: "Gestora Ana",
    is_active: true,
    role: "GESTOR",
    financial_access: "FULL",
    occupation_id: null,
    identification: null,
    document: null,
    birthdate: null,
    number_ctps: null,
    number_oab: null,
    cellphone: null,
    phone: null,
    avatar_url: null,
    salary: null,
    admission_date: null,
    resignation_date: null,
    work_start: null,
    work_interval: null,
    work_end: null,
    points_goal: null,
    report_deadline: false,
    report_deleted: false,
    is_responsible: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "2",
    email: "colaborador@example.com",
    name: "Colaborador Bruno",
    is_active: false,
    role: "COLABORADOR",
    financial_access: "NONE",
    occupation_id: null,
    identification: null,
    document: null,
    birthdate: null,
    number_ctps: null,
    number_oab: null,
    cellphone: null,
    phone: null,
    avatar_url: null,
    salary: null,
    admission_date: null,
    resignation_date: null,
    work_start: null,
    work_interval: null,
    work_end: null,
    points_goal: null,
    report_deadline: false,
    report_deleted: false,
    is_responsible: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

function renderPage(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/settings/users"]}>
        <UsersListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("UsersListPage", () => {
  afterEach(() => server.resetHandlers());

  it("lista filtra por perfil e status", async () => {
    server.use(
      http.get(`${BASE_URL}/api/v1/occupations`, () => HttpResponse.json([])),
      http.get(`${BASE_URL}/api/v1/users`, ({ request }) => {
        const url = new URL(request.url);
        const role = url.searchParams.get("role");
        const status = url.searchParams.get("status");

        let items = ALL_USERS;
        if (role) items = items.filter((item) => item.role === role);
        if (status) {
          const wantActive = status === "active";
          items = items.filter((item) => item.is_active === wantActive);
        }

        return HttpResponse.json({ items, next_cursor: null, total: items.length });
      }),
    );

    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText("Gestora Ana")).toBeInTheDocument();
    expect(screen.getByText("Colaborador Bruno")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Perfil"), "GESTOR");

    await waitFor(() => expect(screen.queryByText("Colaborador Bruno")).not.toBeInTheDocument());
    expect(screen.getByText("Gestora Ana")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Perfil"), "Todos");
    await user.selectOptions(screen.getByLabelText("Status"), "Inativo");

    await waitFor(() => expect(screen.queryByText("Gestora Ana")).not.toBeInTheDocument());
    expect(await screen.findByText("Colaborador Bruno")).toBeInTheDocument();
  });
});
